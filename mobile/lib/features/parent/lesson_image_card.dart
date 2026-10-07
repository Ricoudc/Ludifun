import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/parent.dart';

final lessonImagesProvider = FutureProvider.autoDispose.family<LessonImages, (String, String)>(
  (ref, ids) => ref.watch(apiProvider).lessonImages(ids.$1, ids.$2),
);

/// Fichier d'une image : le chemin change à chaque nouvelle image, il sert de clé.
final imageBytesProvider = FutureProvider.autoDispose.family<Uint8List, String>(
  (ref, path) => ref.watch(apiProvider).imageBytes(path),
);

/// Pendant la préparation, l'état est relu à ce rythme.
const imagePollInterval = Duration(seconds: 10);

/// Image de la leçon (étape 27) : facultative, elle n'est montrée à l'enfant qu'une fois validée
/// par le parent ; refusée, elle peut être refaite avec une remarque.
class LessonImageCard extends ConsumerStatefulWidget {
  const LessonImageCard({required this.childId, required this.lessonId, super.key});

  final String childId;
  final String lessonId;

  @override
  ConsumerState<LessonImageCard> createState() => _LessonImageCardState();
}

class _LessonImageCardState extends ConsumerState<LessonImageCard> {
  Timer? _poll;
  bool _busy = false;

  (String, String) get _ids => (widget.childId, widget.lessonId);

  @override
  void dispose() {
    _poll?.cancel();
    super.dispose();
  }

  /// Relit l'état tant que l'image est en préparation.
  void _follow(LessonImages images) {
    final generating = images.image?.status == ImageStatus.generating;
    if (generating && _poll == null) {
      _poll = Timer.periodic(imagePollInterval, (_) => ref.invalidate(lessonImagesProvider(_ids)));
    } else if (!generating) {
      _poll?.cancel();
      _poll = null;
    }
  }

  Future<void> _act(Future<LessonImage> Function() action, String done) async {
    setState(() => _busy = true);
    String message;
    try {
      await action();
      message = done;
    } on ApiException catch (error) {
      message = error.message;
    }
    if (!mounted) return;
    setState(() => _busy = false);
    ref.invalidate(lessonImagesProvider(_ids));
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _redo() async {
    final remark = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _RedoSheet(),
    );
    if (remark == null || !mounted) return;
    final api = ref.read(apiProvider);
    await _act(
      () => api.redoImage(widget.childId, widget.lessonId, remark: remark.isEmpty ? null : remark),
      'Nouvelle image demandée : elle sera prête dans quelques minutes.',
    );
  }

  @override
  Widget build(BuildContext context) {
    final images = ref.watch(lessonImagesProvider(_ids));
    final value = images.value;
    if (value == null) return const SizedBox();
    _follow(value);
    final image = value.image;
    // Pas de moteur d'images et rien de préparé : la carte ne sert à rien.
    if (image == null && !value.available) return const SizedBox();
    final api = ref.read(apiProvider);
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                const Icon(Icons.image_outlined),
                const SizedBox(width: 12),
                Expanded(
                  child: Text('Image de la leçon', style: Theme.of(context).textTheme.titleMedium),
                ),
              ],
            ),
            const SizedBox(height: 6),
            Text(_statusText(image), style: const TextStyle(fontSize: 14, color: Colors.black54)),
            if (image?.url case final url?) ...[
              const SizedBox(height: 12),
              _ImagePreview(url: url, alt: image?.alt),
            ],
            if (image?.alt case final alt?) ...[
              const SizedBox(height: 6),
              Text(alt, style: const TextStyle(fontSize: 14, fontStyle: FontStyle.italic)),
            ],
            if (image?.remark case final remark?) ...[
              const SizedBox(height: 6),
              Text(
                'Votre remarque : « $remark »',
                style: const TextStyle(fontSize: 14, color: Colors.black54),
              ),
            ],
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                if (image != null &&
                    image.url != null &&
                    image.status != ImageStatus.approved &&
                    image.status != ImageStatus.generating)
                  FilledButton.icon(
                    onPressed: _busy
                        ? null
                        : () => _act(
                            () => api.approveImage(widget.childId, widget.lessonId),
                            'Image validée : l\'enfant la verra avec sa leçon.',
                          ),
                    icon: const Icon(Icons.check),
                    label: const Text('Valider'),
                  ),
                if (image != null &&
                    image.url != null &&
                    (image.status == ImageStatus.toReview || image.status == ImageStatus.approved))
                  OutlinedButton.icon(
                    onPressed: _busy
                        ? null
                        : () => _act(
                            () => api.rejectImage(widget.childId, widget.lessonId),
                            'Image refusée : l\'enfant ne la verra pas.',
                          ),
                    icon: const Icon(Icons.close),
                    label: const Text('Refuser'),
                  ),
                if (value.available && image?.status != ImageStatus.generating)
                  OutlinedButton.icon(
                    onPressed: _busy ? null : _redo,
                    icon: const Icon(Icons.refresh),
                    label: Text(image == null ? 'Créer une image' : 'Refaire'),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

String _statusText(LessonImage? image) => switch (image?.status) {
  null =>
    'Pas d\'image pour cette leçon. Elle est facultative : les questions n\'en dépendent pas.',
  ImageStatus.generating => 'Image en préparation… (quelques minutes)',
  ImageStatus.toReview =>
    'À valider : l\'enfant ne la verra qu\'après votre accord. Elle est facultative.',
  ImageStatus.approved => 'Validée : l\'enfant la voit avec sa leçon.',
  ImageStatus.rejected => 'Refusée : l\'enfant ne la voit pas. Vous pouvez demander de la refaire.',
  ImageStatus.failed =>
    'L\'image n\'a pas pu être faite${image?.error == null ? '' : ' (${image!.error})'}. '
        'La leçon, elle, est complète.',
};

class _ImagePreview extends ConsumerWidget {
  const _ImagePreview({required this.url, this.alt});

  final String url;
  final String? alt;

  @override
  Widget build(BuildContext context, WidgetRef ref) => switch (ref.watch(imageBytesProvider(url))) {
    AsyncData(:final value) => ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: Image.memory(
        value,
        semanticLabel: alt,
        fit: BoxFit.contain,
        errorBuilder: (_, _, _) => const Text('Image illisible.'),
      ),
    ),
    AsyncError() => const Text('Image indisponible pour le moment.'),
    _ => const SizedBox(height: 120, child: Center(child: CircularProgressIndicator())),
  };
}

class _RedoSheet extends StatefulWidget {
  const _RedoSheet();

  @override
  State<_RedoSheet> createState() => _RedoSheetState();
}

class _RedoSheetState extends State<_RedoSheet> {
  final _remark = TextEditingController();

  @override
  void dispose() {
    _remark.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.fromLTRB(24, 24, 24, 24 + MediaQuery.viewInsetsOf(context).bottom),
    child: Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('Refaire l\'image', style: Theme.of(context).textTheme.titleLarge),
        const SizedBox(height: 12),
        TextField(
          controller: _remark,
          maxLength: 300,
          maxLines: 3,
          decoration: const InputDecoration(
            labelText: 'Qu\'est-ce qui ne va pas ? (facultatif)',
            hintText: 'Par exemple : « montrer plutôt un arbre en automne »',
          ),
        ),
        const SizedBox(height: 8),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(_remark.text.trim()),
          child: const Text('Refaire l\'image'),
        ),
      ],
    ),
  );
}
