import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
p=argparse.ArgumentParser();p.add_argument('--build',required=True);p.add_argument('--compiler',required=True)
a=p.parse_args();root=Path(__file__).resolve().parent;build=Path(a.build);target=build/'h60-forward-3s'
binary=target.with_suffix('.bin').read_bytes()
if len(binary)>16384 or len(binary)%4 or b'H60_FORWARD3S_SINGLE_SHOT_V1\0' not in binary:
    raise SystemExit('Imagen fuera de sector0/alineación/marcador.')
files=[root/'Makefile',root/'build_manifest.py',root/'vendor-lock.json']
for part in ('src','include','vendor','tests','build_support'):
    files.extend(f for f in (root/part).rglob('*') if f.is_file() and f.suffix.lower() in ('.c','.h','.s','.ld','.py'))
sources={str(f.relative_to(root)):digest(f) for f in sorted(files)}
caps=struct.pack('>BBBBHHHHII',1,4,15,10,100,5000,3,3000,3005000,100)+b'H60_FORWARD3S_SINGLE_SHOT_V1'
record={'schema':'h60.forward-3s-build.v1','target':'STM32F407VE','profile':4,
        'marker':'H60_FORWARD3S_SINGLE_SHOT_V1','motor_capable':True,
        'fixed_motor_channels':['A','B','C','D'],'fixed_motor_mask':15,
        'fixed_reversed_mask':10,'fixed_raw_directions':[1,-1,1,-1],
        'uart':1,'uart_pins':['PA9','PA10'],'baudrate':230400,'framing':'8N1',
        'duty_permille':100,'pwm_hz':5000,'pwm_duration_ms':3000,'wake_min_ms':3,
        'absolute_envelope_us':3005000,'lease_ms':100,'one_fire_per_boot':True,
        'caps_hex':caps.hex(),'nonce_source':'STM32F407 hardware RNG, bounded failure -> FAULT',
        'hardware_cutoff':'No autonomous timer cutoff for this3s candidate; TIM1RCR0, noOPM',
        'software_cutoff':'All motors: SysTick priority0 and main loop/DWT3000ms; global3005ms; IWDG backup',
        'off_readback':'GPIO MODER/ODR/IDR and TIM1/9/12 controls; not external motor voltage measurement',
        'image_bytes':len(binary),'payload_sha256':hashlib.sha256(binary).hexdigest(),
        'artifacts':{target.with_suffix(ext).name:digest(target.with_suffix(ext)) for ext in ('.elf','.bin','.hex','.map')},
        'sources':sources,'compiler':subprocess.check_output([a.compiler,'--version'],text=True).splitlines()[0],
        'build_flags':['-mcpu=cortex-m4','-mthumb','-mfpu=fpv4-sp-d16','-mfloat-abi=hard','-Os'],
        'hardware_tested':False}
(build/'manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({k:record[k] for k in ('schema','image_bytes','payload_sha256','motor_capable')},indent=2))
