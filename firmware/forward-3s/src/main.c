/* Prueba conjunta de avance de3s: A/C positivo, B/D negativo. */
#include "stm32f4xx.h"
#include "ax_encoder.h"
#include "clock_validation.h"
#include "pulse.h"

#define E_PINS ((1u<<5)|(1u<<6)|(1u<<9)|(1u<<11)|(1u<<13)|(1u<<14))
#define B_PINS ((1u<<14)|(1u<<15))
_Static_assert(PULSE_CHANNEL_MASK==15u,"Esta imagen caracteriza los cuatro motores.");
_Static_assert(PULSE_REVERSED_MASK==10u,"La corrección de avance invierte B y D.");
#define RX_COUNT 64u
static Pulse state;
static volatile uint32_t milliseconds, last_isr_cycles;
static volatile bool kill_latch, hardware_started;
static volatile uint32_t fire_cycles,pwm_cycles;
typedef struct { uint32_t arrival; uint8_t value; } Rx;
static Rx rx[RX_COUNT];
static volatile uint8_t head,tail;
const char artifact_marker[] __attribute__((used,section(".firmware_signature")))=PULSE_MARKER;

static uint32_t mode_mask(uint32_t pins)
{
    uint32_t mask=0;for(unsigned i=0;i<16;i++)if(pins&(1u<<i))mask|=3u<<(i*2);
    return mask;
}
static uint32_t out_mode(uint32_t pins)
{
    uint32_t mask=0;for(unsigned i=0;i<16;i++)if(pins&(1u<<i))mask|=1u<<(i*2);
    return mask;
}
static void motors_off(void)
{
    RCC->AHB1ENR|=RCC_AHB1ENR_GPIOBEN|RCC_AHB1ENR_GPIOEEN;
    RCC->APB2ENR|=RCC_APB2ENR_TIM1EN|RCC_APB2ENR_TIM9EN;
    RCC->APB1ENR|=RCC_APB1ENR_TIM12EN;
    __DSB();
    TIM1->BDTR&=~TIM_BDTR_MOE;
    TIM1->CR1&=~TIM_CR1_CEN;TIM9->CR1&=~TIM_CR1_CEN;TIM12->CR1&=~TIM_CR1_CEN;
    TIM1->CCER=0;TIM9->CCER=0;TIM12->CCER=0;
    GPIOE->BSRRH=E_PINS;GPIOB->BSRRH=B_PINS;
    GPIOE->MODER=(GPIOE->MODER&~mode_mask(E_PINS))|out_mode(E_PINS);
    GPIOB->MODER=(GPIOB->MODER&~mode_mask(B_PINS))|out_mode(B_PINS);
    GPIOE->OTYPER&=~E_PINS;GPIOB->OTYPER&=~B_PINS;
    GPIOE->PUPDR&=~mode_mask(E_PINS);GPIOB->PUPDR&=~mode_mask(B_PINS);
    hardware_started=false;__DSB();
}
static bool all_low(void)
{
    return (GPIOE->MODER&mode_mask(E_PINS))==out_mode(E_PINS) &&
           (GPIOB->MODER&mode_mask(B_PINS))==out_mode(B_PINS) &&
           !(GPIOE->ODR&E_PINS) && !(GPIOB->ODR&B_PINS) &&
           !(GPIOE->IDR&E_PINS) && !(GPIOB->IDR&B_PINS) &&
           !(TIM1->CR1&TIM_CR1_CEN) && !(TIM1->BDTR&TIM_BDTR_MOE) &&
           !(TIM9->CR1&TIM_CR1_CEN) && !(TIM12->CR1&TIM_CR1_CEN);
}
void JUANILLO_FatalStop(void) __attribute__((noreturn));
void JUANILLO_FatalStop(void)
{
    __disable_irq();kill_latch=true;motors_off();
    for(;;)__WFI();
}
void assert_failed(uint8_t *file,uint32_t line)
{
    (void)file;(void)line;JUANILLO_FatalStop();
}
static void counts(uint16_t out[4])
{
    out[0]=AX_ENCODER_A_GetCounter();out[1]=AX_ENCODER_B_GetCounter();
    out[2]=AX_ENCODER_C_GetCounter();out[3]=AX_ENCODER_D_GetCounter();
}
static void configure_pwm(void)
{
    /* Tres segundos exceden RCR8bit: TODOS dependen de corte software
       DWT/SysTick y del IWDG; no se declara corte autónomo de temporizador. */
    TIM1->CR1=TIM_CR1_ARPE;TIM1->CR2=0;TIM1->SMCR=0;TIM1->DIER=0;
    TIM1->PSC=7;TIM1->ARR=4199;TIM1->RCR=0;
    TIM1->CCR1=4200;TIM1->CCR2=3780;TIM1->CCR3=3780;TIM1->CCR4=4200;
    TIM1->CCMR1=(6u<<4)|TIM_CCMR1_OC1PE|(6u<<12)|TIM_CCMR1_OC2PE;
    TIM1->CCMR2=(6u<<4)|TIM_CCMR2_OC3PE|(6u<<12)|TIM_CCMR2_OC4PE;
    TIM1->CCER=TIM_CCER_CC1E|TIM_CCER_CC2E|TIM_CCER_CC3E|TIM_CCER_CC4E;
    TIM1->BDTR=TIM_BDTR_OSSI|TIM_BDTR_OSSR;
    TIM1->EGR=TIM_EGR_UG;TIM1->SR=0;TIM1->CNT=0;
}
static void configure_two_channel(TIM_TypeDef *timer,uint16_t prescaler,bool reverse)
{
    /* TIM9/TIM12 carecen de RCR/BDTR; no se accede a esos registros.
       El corte de C/D depende del bucle/ISR+DWT, con IWDG de respaldo. */
    timer->CR1=TIM_CR1_ARPE;timer->SMCR=0;timer->DIER=0;
    timer->PSC=prescaler;timer->ARR=4199;
    timer->CCR1=reverse?3780:4200;timer->CCR2=reverse?4200:3780;
    timer->CCMR1=(6u<<4)|TIM_CCMR1_OC1PE|(6u<<12)|TIM_CCMR1_OC2PE;
    timer->CCER=TIM_CCER_CC1E|TIM_CCER_CC2E;
    timer->EGR=TIM_EGR_UG;timer->SR=0;timer->CNT=0;
}
static void apply(uint8_t event)
{
    if((event&E_OFF) || kill_latch || state.state==P_FAULT) { motors_off();return; }
    if(event&E_WAKE) {
        if(state.state!=P_WAKE || !state.consumed || hardware_started || !all_low()) {
            kill_latch=true;pulse_fault(&state,R_HARDWARE);motors_off();return;
        }
        fire_cycles=DWT->CYCCNT;
        GPIOE->BSRRL=E_PINS;GPIOB->BSRRL=B_PINS; /* 11 en los cuatro puentes. */
    }
    if(event&E_PWM) {
        uint32_t elapsed=DWT->CYCCNT-fire_cycles;
        if(state.state!=P_RUNNING || hardware_started || !state.consumed ||
           elapsed<3u*(SystemCoreClock/1000u) || elapsed>4u*(SystemCoreClock/1000u)) {
            kill_latch=true;pulse_fault(&state,R_LATE);motors_off();return;
        }
        configure_pwm();
        configure_two_channel(TIM9,7,false); /* C: positivo; APB2 timer=168MHz. */
        configure_two_channel(TIM12,3,true); /* D: negativo; APB1 timer=84MHz. */
        GPIOE->AFR[0]=(GPIOE->AFR[0]&~((15u<<20)|(15u<<24)))|(3u<<20)|(3u<<24);
        GPIOE->AFR[1]=(GPIOE->AFR[1]&~((15u<<4)|(15u<<12)|(15u<<20)|(15u<<24)))|
                     (1u<<4)|(1u<<12)|(1u<<20)|(1u<<24);
        GPIOB->AFR[1]=(GPIOB->AFR[1]&~((15u<<24)|(15u<<28)))|(9u<<24)|(9u<<28);
        GPIOE->MODER=(GPIOE->MODER&~mode_mask(E_PINS))|(out_mode(E_PINS)<<1);
        GPIOB->MODER=(GPIOB->MODER&~mode_mask(B_PINS))|(out_mode(B_PINS)<<1);
        /* Guardar el margen tras configurar, antes de habilitar MOE/CEN. */
        if(DWT->CYCCNT-fire_cycles>4u*(SystemCoreClock/1000u)) {
            kill_latch=true;pulse_fault(&state,R_LATE);motors_off();return;
        }
        pwm_cycles=DWT->CYCCNT;hardware_started=true;
        TIM1->BDTR|=TIM_BDTR_MOE;TIM1->CR1|=TIM_CR1_CEN;
        TIM9->CR1|=TIM_CR1_CEN;TIM12->CR1|=TIM_CR1_CEN;__DSB();
    }
}
static bool pwm_finished(void)
{
    return hardware_started && (!(TIM1->CR1&TIM_CR1_CEN) ||
        DWT->CYCCNT-pwm_cycles>=PULSE_PWM_MS*(SystemCoreClock/1000u) ||
        DWT->CYCCNT-fire_cycles>=PULSE_ENVELOPE_MS*(SystemCoreClock/1000u));
}
void SysTick_Handler(void)
{
    uint32_t now_cycles=DWT->CYCCNT;
    if((uint32_t)(now_cycles-last_isr_cycles)>2u*(SystemCoreClock/1000u)) {
        kill_latch=true;pulse_fault(&state,R_LATE);motors_off();
    }
    last_isr_cycles=now_cycles;milliseconds++;
    uint16_t enc[4];counts(enc);
    uint8_t event=pulse_observe(&state,enc,milliseconds);
    event|=pulse_tick(&state,milliseconds,pwm_finished());
    apply(event);
}
void USART1_IRQHandler(void)
{
    uint32_t status=USART1->SR;
    if(status&(USART_SR_RXNE|USART_SR_ORE|USART_SR_NE|USART_SR_FE|USART_SR_PE)) {
        uint8_t byte=(uint8_t)USART1->DR;
        uint8_t next=(uint8_t)((head+1u)%RX_COUNT);
        if((status&(USART_SR_ORE|USART_SR_NE|USART_SR_FE|USART_SR_PE)) || next==tail) {
            kill_latch=true;motors_off();return;
        }
        rx[head].value=byte;rx[head].arrival=milliseconds;__DMB();head=next;
    }
}
static void uart_init(void)
{
    RCC->AHB1ENR|=RCC_AHB1ENR_GPIOAEN;RCC->APB2ENR|=RCC_APB2ENR_USART1EN;__DSB();
    GPIOA->AFR[1]=(GPIOA->AFR[1]&~((15u<<4)|(15u<<8)))|(7u<<4)|(7u<<8);
    GPIOA->MODER=(GPIOA->MODER&~((3u<<18)|(3u<<20)))|(2u<<18)|(2u<<20);
    GPIOA->OTYPER&=~((1u<<9)|(1u<<10));
    GPIOA->PUPDR=(GPIOA->PUPDR&~((3u<<18)|(3u<<20)))|(1u<<18)|(1u<<20);
    USART1->CR1=0;USART1->CR2=0;USART1->CR3=USART_CR3_EIE;
    USART1->BRR=365; /* APB2=84MHz: 230400 baudios, error inferior a0,12%. */
    NVIC_SetPriority(USART1_IRQn,3);NVIC_EnableIRQ(USART1_IRQn);
    USART1->CR1=USART_CR1_UE|USART_CR1_TE|USART_CR1_RE|USART_CR1_RXNEIE;
}
static bool transmit(const uint8_t *data,size_t length)
{
    for(size_t i=0;i<length;i++) {
        uint32_t started=DWT->CYCCNT;
        while(!(USART1->SR&USART_SR_TXE)) {
            if(DWT->CYCCNT-started>SystemCoreClock/10000u) return false;
        }
        USART1->DR=data[i];
    }
    return true;
}
static bool rng_word(uint32_t *out)
{
    uint32_t started=DWT->CYCCNT;
    for(;;) {
        uint32_t status=RNG->SR;
        if(status&0x66u)return false;
        if(status&1u) { *out=RNG->DR;return true; }
        if(DWT->CYCCNT-started>SystemCoreClock/200u)return false;
    }
}
static uint64_t boot_nonce(void)
{
    uint32_t a,b;
    RCC->AHB2ENR|=RCC_AHB2ENR_RNGEN;__DSB();RNG->CR=RNG_CR_RNGEN;
    if(!rng_word(&a)||!rng_word(&b)||!a||!b||a==b)return 0;
    RNG->CR=0;
    return ((uint64_t)a<<32)|b;
}
int main(void)
{
    motors_off();SystemCoreClockUpdate();
    if(!JUANILLO_ClockRegistersValid(RCC->CR,RCC->CFGR,RCC->PLLCFGR,SystemCoreClock))JUANILLO_FatalStop();
    CoreDebug->DEMCR|=CoreDebug_DEMCR_TRCENA_Msk;DWT->CYCCNT=0;DWT->CTRL|=DWT_CTRL_CYCCNTENA_Msk;
    AX_ENCODER_A_Init();AX_ENCODER_B_Init();AX_ENCODER_C_Init();AX_ENCODER_D_Init();
    pulse_init(&state,boot_nonce(),0);
    uart_init();
    NVIC_SetPriority(SysTick_IRQn,0);last_isr_cycles=DWT->CYCCNT;
    SysTick->LOAD=SystemCoreClock/1000u-1u;SysTick->VAL=0;
    SysTick->CTRL=SysTick_CTRL_CLKSOURCE_Msk|SysTick_CTRL_TICKINT_Msk|SysTick_CTRL_ENABLE_Msk;
    /* Respaldo, sin reclamar un plazo eléctrico exacto del oscilador LSI. */
    IWDG->KR=0x5555;IWDG->PR=0;IWDG->RLR=127;IWDG->KR=0xAAAA;IWDG->KR=0xCCCC;
    for(;;) {
        uint8_t packet[64],payload[48];size_t send_length=0;
        uint32_t saved=__get_PRIMASK();__disable_irq();
        if(kill_latch || DWT->CYCCNT-last_isr_cycles>3u*(SystemCoreClock/1000u)) {
            kill_latch=true;apply(pulse_fault(&state,R_LATE));
        }
        uint8_t event=pulse_tick(&state,milliseconds,pwm_finished());
        if(tail!=head) {
            Rx sample=rx[tail];tail=(uint8_t)((tail+1u)%RX_COUNT);
            if((uint32_t)(milliseconds-sample.arrival)>10u)event|=pulse_fault(&state,R_FRAME);
            else event|=pulse_feed(&state,sample.value,milliseconds);
        }
        apply(event);
        if(event&E_REPLY) {
            if(event&E_CAPS) { pulse_caps(payload);send_length=pulse_packet(state.reply_id,payload,48,packet); }
            else if(event&E_ENCODERS) {
                for(unsigned i=0;i<4;i++) { payload[2*i]=(uint8_t)(state.counters[i]>>8);payload[2*i+1]=(uint8_t)state.counters[i]; }
                send_length=pulse_packet(state.reply_id,payload,8,packet);
            } else { pulse_status(&state,milliseconds,all_low(),payload);send_length=pulse_packet(state.reply_id,payload,36,packet); }
        }
        __set_PRIMASK(saved);
        if(send_length && !transmit(packet,send_length)) {
            __disable_irq();kill_latch=true;pulse_fault(&state,R_HARDWARE);motors_off();__set_PRIMASK(saved);
        }
        /* Un FAULT queda consultable si el bucle y la ISR progresan y los
           registros/pines confirman00. Un bloqueo de CPU/ISR no se alimenta. */
        uint32_t feed_saved=__get_PRIMASK();__disable_irq();
        bool outputs_safe=state.state==P_FAULT?all_low():!kill_latch;
        if(outputs_safe && DWT->CYCCNT-last_isr_cycles<3u*(SystemCoreClock/1000u))IWDG->KR=0xAAAA;
        __set_PRIMASK(feed_saved);
    }
}
