# Dice Wallet Worksheet

A one-page, print-ready worksheet for creating a [SeedSigner](https://seedsigner.com/)
Bitcoin wallet from physical dice rolls, including a dice-generated
hexadecimal BIP-39 passphrase.

Generates a single letter-size PDF with four main sections:

1. **Dice Rolls** — a 10x10 grid for recording d6 rolls, supporting both
   50-roll (12-word) and 99-roll (24-word) seed flows.
2. **Seed Words** — numbered blank lines for the resulting BIP-39 mnemonic.
3. **Seed QR** — three blank QR templates sized for SeedSigner output.
4. **Dice Generated Hexadecimal Passphrase** — a dice-to-hex lookup and
   passphrase grid for recording a 32-digit (128-bit) value.

A notes section is included at the bottom for any extra notes or wallet details.

<p align="center">
  <img src="preview.png" width="500" alt="Worksheet preview">
</p>

## Usage

```bash
pip3 install -r requirements.txt
python3 generate_worksheet.py
```

The PDF is written to `output/dice_wallet_worksheet.pdf` by default. Use
`-o` to write elsewhere:

```bash
python3 generate_worksheet.py -o ~/Desktop/worksheet.pdf
```

## Security

This worksheet is meant to hold sensitive wallet material once filled
out. Treat a completed copy the same as any other seed backup: store it
securely (e.g. safe, safety deposit box) or destroy it after transferring
the wallet to its permanent storage, never photograph or scan it, and
never enter its contents into an internet-connected device except through
SeedSigner's own dice-entry flow.

## Attribution

This project includes QR template assets and the fingerprint icon adapted
from the SeedSigner project, which are licensed under the MIT License.
Copyright (c) 2021 SeedSigner.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

## Disclaimer

This project is provided for educational and convenience purposes only.
It is offered as-is, without warranty of any kind, express or implied,
including any warranty of merchantability, fitness for a particular purpose,
or non-infringement.

Use of this worksheet is entirely at the user's own risk. Users are solely
responsible for verifying the security, correctness, legality, and suitability
of their own use case. The author makes no guarantees about compatibility,
recovery accuracy, or operational safety, and is not liable for any loss,
damage, or other consequences arising from the use of this project.
