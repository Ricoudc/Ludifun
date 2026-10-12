import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

/// Préfixe du QR code affiché dans l'espace parent (§11).
const qrPrefix = 'ludifun://lier/';

/// Écran 0 bis : lecture du QR code affiché sur le téléphone du parent. Rend son contenu.
class QrScanScreen extends StatefulWidget {
  const QrScanScreen({super.key});

  @override
  State<QrScanScreen> createState() => _QrScanScreenState();
}

class _QrScanScreenState extends State<QrScanScreen> {
  bool _done = false;

  void _onDetect(BarcodeCapture capture) {
    if (_done) return;
    for (final barcode in capture.barcodes) {
      final value = barcode.rawValue;
      if (value != null && value.startsWith(qrPrefix)) {
        _done = true;
        context.pop(value);
        return;
      }
    }
  }

  @override
  Widget build(BuildContext context) => Scaffold(
    backgroundColor: Colors.black,
    appBar: AppBar(
      backgroundColor: Colors.black,
      foregroundColor: Colors.white,
      title: const Text('Scanne le QR code'),
    ),
    body: Stack(
      alignment: Alignment.center,
      children: [
        MobileScanner(
          onDetect: _onDetect,
          errorBuilder: (context, error) => const Padding(
            padding: EdgeInsets.all(32),
            child: Text(
              'Je n\'arrive pas à ouvrir l\'appareil photo. Tu peux saisir le code à la place.',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.white, fontSize: 18),
            ),
          ),
        ),
        IgnorePointer(
          child: Container(
            width: 260,
            height: 260,
            decoration: BoxDecoration(
              border: Border.all(color: Colors.white, width: 4),
              borderRadius: BorderRadius.circular(24),
            ),
          ),
        ),
        const Positioned(
          bottom: 48,
          child: Text(
            'Vise le QR code sur le téléphone de ton parent.',
            style: TextStyle(color: Colors.white, fontSize: 16),
          ),
        ),
      ],
    ),
  );
}
