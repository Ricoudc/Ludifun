import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/widgets.dart';

/// Écrans 5 à 7 (jeu, correction, bilan) : étape 11. La séance existe déjà côté serveur.
class SessionScreen extends StatelessWidget {
  const SessionScreen({required this.sessionId, super.key});

  final String sessionId;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(leading: CloseButton(onPressed: () => context.go(Routes.childHome))),
    body: const CenteredBody(
      children: [
        Text('🎮', textAlign: TextAlign.center, style: TextStyle(fontSize: 64)),
        SizedBox(height: 16),
        Text(
          'Ta séance est prête ! Les jeux arrivent très bientôt.',
          textAlign: TextAlign.center,
          style: TextStyle(fontSize: 20),
        ),
      ],
    ),
  );
}
