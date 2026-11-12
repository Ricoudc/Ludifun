import 'package:flutter/material.dart';

import '../../app/widgets.dart';

/// Pendant la lecture des identifiants dans le stockage sécurisé.
class SplashScreen extends StatelessWidget {
  const SplashScreen({super.key});

  @override
  Widget build(BuildContext context) => const Scaffold(
    body: CenteredBody(
      children: [
        Logo(),
        SizedBox(height: 32),
        Center(child: CircularProgressIndicator()),
      ],
    ),
  );
}
