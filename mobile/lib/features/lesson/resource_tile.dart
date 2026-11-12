import 'package:flutter/material.dart';

import '../../models/resource.dart';
import 'resource_screen.dart';

/// Exercice, quiz ou vidéo d'un site de confiance (étape 30), ouvert dans l'application
/// (écran de la leçon et « Mon cahier »).
class ResourceTile extends StatelessWidget {
  const ResourceTile({required this.lessonId, required this.resource, this.onClosed, super.key});

  final String lessonId;
  final LessonResource resource;

  /// Au retour de la visionneuse (un meilleur score a pu changer).
  final VoidCallback? onClosed;

  @override
  Widget build(BuildContext context) => ListTile(
    contentPadding: EdgeInsets.zero,
    dense: true,
    leading: Text(resource.provider.emoji, style: const TextStyle(fontSize: 26)),
    title: Text(resource.title, style: const TextStyle(fontSize: 18)),
    subtitle: Text(
      '${resource.kind.label} · ${resource.provider.label}'
      '${resource.best == null ? '' : ' · meilleur score ${resource.best}'}',
    ),
    trailing: const Icon(Icons.chevron_right),
    onTap: () async {
      await Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => ResourceScreen(resource: resource, lessonId: lessonId),
        ),
      );
      onClosed?.call();
    },
  );
}
