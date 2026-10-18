# Codec source

Extracted from [Barista](https://github.com/BetaZay/Barista), base commit
`081ca2fe0a4caa11fb8e120319fc5aa1bd5380cf` (GPL-2.0; see LICENSE).
This snapshot includes local macOS/Apple Silicon compatibility changes:
64-bit-safe pointer alignment checks, the Apple NEON table-lookup intrinsic,
an explicit bitstream pointer cast, and the CABAC coefficient-order correction.
NEON coefficients retain identity indexing rather than the SSE transposition. It also retains the native GamePad encoder
compatibility settings present in the working source.

The bundled minih264-derived code retains its separate notices in
`drh/encoder/x264/MINIH264_LICENSE` and `MINIH264_UPSTREAM.md`.
