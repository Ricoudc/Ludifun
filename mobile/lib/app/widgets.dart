import 'package:flutter/material.dart';

import 'theme.dart';

/// Contenu centré et lisible sur téléphone comme sur tablette.
class CenteredBody extends StatelessWidget {
  const CenteredBody({required this.children, this.top = false, super.key});

  final List<Widget> children;

  /// Listes : contenu en haut de l'écran plutôt qu'au milieu.
  final bool top;

  @override
  Widget build(BuildContext context) => SafeArea(
    child: Align(
      alignment: top ? Alignment.topCenter : Alignment.center,
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(), // tirer pour actualiser
        padding: const EdgeInsets.all(24),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 480),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: children,
          ),
        ),
      ),
    ),
  );
}

class Logo extends StatelessWidget {
  const Logo({super.key});

  @override
  Widget build(BuildContext context) => Text(
    'Ludifun',
    textAlign: TextAlign.center,
    style: Theme.of(context).textTheme.displaySmall
        ?.copyWith(color: LudiColors.primary, fontWeight: FontWeight.w900),
  );
}

class ErrorMessage extends StatelessWidget {
  const ErrorMessage(this.message, {super.key});

  final String message;

  @override
  Widget build(BuildContext context) => Semantics(
    liveRegion: true,
    child: Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: LudiColors.notMastered.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Text(message, style: const TextStyle(color: LudiColors.notMastered, fontSize: 16)),
    ),
  );
}
