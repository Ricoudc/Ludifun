import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/session.dart';

/// Fichier d'une image du serveur (images des leçons et des notions), lu avec le jeton du parent
/// ou de l'appareil. Le chemin vient du serveur ; il sert de clé.
final imageBytesProvider = FutureProvider.autoDispose.family<Uint8List, String>(
  (ref, path) => ref.watch(apiProvider).imageBytes(path),
);

/// Une image du serveur ; pendant le chargement, un rond qui tourne ; illisible ou absente
/// (refusée entre-temps par le parent), [fallback].
class ApiImage extends ConsumerWidget {
  const ApiImage(
    this.path, {
    this.semanticLabel,
    this.fit = BoxFit.cover,
    this.fallback = const Center(child: Text('🖼️', style: TextStyle(fontSize: 32))),
    super.key,
  });

  final String path;
  final String? semanticLabel;
  final BoxFit fit;
  final Widget fallback;

  @override
  Widget build(BuildContext context, WidgetRef ref) =>
      switch (ref.watch(imageBytesProvider(path))) {
        AsyncData(:final value) => Image.memory(
          value,
          semanticLabel: semanticLabel,
          excludeFromSemantics: semanticLabel == null,
          fit: fit,
          errorBuilder: (_, _, _) => fallback,
        ),
        AsyncError() => fallback,
        _ => const Center(child: CircularProgressIndicator()),
      };
}
