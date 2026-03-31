# Bench / FPGA Bring-up Checklist

- Apply reset and confirm all QSPI outputs are tri-stated during reset.
- Release reset and confirm `uo[0]` idles high as UART TX.
- Send one UART RX byte on `ui[7]` and confirm the SoC receives it.
- Observe one UART TX byte on `uo[0]`.
- Perform one GPIO output write and confirm the expected `uo[7:1]` pin changes in GPIO mode.
- Toggle `ui[0]` and confirm `uo[7:1]` switches from GPIO view to debug view while `uo[0]` remains UART TX.
- Step `ui[4:1]` through multiple values in debug mode and confirm `uo[1]` follows the selected debug probe while `uo[7:2]` remain fixed status bits.
- Pulse `ui[0]`/`ui[1]` as external IRQ sources and confirm the debug/firmware-visible interrupt path behaves as expected.
