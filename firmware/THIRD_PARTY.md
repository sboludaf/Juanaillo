The public source tree excludes third-party firmware code and binaries.

`forward-3s/vendor-lock.json` identifies only the dependencies needed by that
candidate. The importer accepts the user's original `OpenCTR H60 code.zip`, its
two relevant inner ZIPs, or a directory containing their extracted package
roots. It verifies each pristine file before writing a local ignored copy.

- XTARK encoder source and header: the supplied files identify XTARK and retain
  copyright notices. No standalone license granting redistribution was found in
  the supplied outer ZIP. They are not covered by this project's license.
- STMicroelectronics device headers, standard peripheral library, configuration,
  system code and startup: supplied notices identify MCD-ST Liberty SW License
  Agreement V2. The source headers refer to
  `http://www.st.com/software_license_agreement_liberty_v2`.
- ARM CMSIS core headers: supplied source headers contain ARM's own copyright
  and license notices. Preserve and consult those notices in your local import.
- The startup import normalizes line endings and changes only the default
  interrupt-handler branch to `JUANILLO_FatalStop`; pristine and resulting
  hashes are both locked. The vendor source is not embedded in the importer.
- The linker script and clock-validation helpers in `forward-3s/build_support/`
  are project-written files. Commissioning contains only project-written
  modules and fake test backends, not the earlier mixed vendor application.

No license claim in this repository grants additional rights to the vendor kit.
