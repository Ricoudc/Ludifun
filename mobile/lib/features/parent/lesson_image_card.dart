import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../app/api_image.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/parent.dart';

final lessonImagesProvider = FutureProvider.autoDispose.family<LessonImages, (String, String)>(
  (ref, ids) => ref.watch(apiProvider).lessonImages(ids.$1, ids.$2),
);

/// Pendant la préparation, l'état est relu à ce rythme.
const imagePollInterval = Duration(seconds: 10);

/// Images de la leçon (étapes 27 et 28) : facultatives, chacune n'est montrée à l'enfant qu'une
/// fois validée par le parent ; refusée, elle peut être refaite avec une remarque. L'IA ne dessine
/// que si une image aide à retenir la leçon (sinon « pas utile ») ; les images des notions
/// concrètes servent aux jeux « Image et mot » et « Quelle image ? ».
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

  /// Relit l'état tant qu'une image est en préparation.
  void _follow(LessonImages images) {
    if (images.pending && _poll == null) {
      _poll = Timer.periodic(imagePollInterval, (_) => ref.invalidate(lessonImagesProvider(_ids)));
    } else if (!images.pending) {
      _poll?.cancel();
      _poll = null;
    }
  }

  Future<void> _act(Future<Object?> Function() action, String done) async {
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

  Future<void> _redo(LessonImage? image) async {
    final remark = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      builder: (_) => const _RedoSheet(),
    );
    if (remark == null || !mounted) return;
    final api = ref.read(apiProvider);
    final note = remark.isEmpty ? null : remark;
    final (child, lesson) = _ids;
    await _act(
      () => switch (image) {
        LessonImage(knowledgeId: _?, id: final id?) => api.redoPicture(
          child,
          lesson,
          id,
          remark: note,
        ),
        _ => api.redoImage(child, lesson, remark: note),
      },
      'Nouvelle image demandée : elle sera prête dans quelques minutes.',
    );
  }

  Future<void> _decide(LessonImage image, {required bool approve}) {
    final api = ref.read(apiProvider);
    final (child, lesson) = _ids;
    final picture = image.knowledgeId != null && image.id != null;
    return _act(
      () => switch ((picture, approve)) {
        (true, _) => api.decidePicture(child, lesson, image.id!, approve: approve),
        (false, true) => api.approveImage(child, lesson),
        (false, false) => api.rejectImage(child, lesson),
      },
      approve
          ? (picture
                ? 'Image validée : l\'enfant la voit avec la notion et dans les jeux en images.'
                : 'Image validée : l\'enfant la verra avec sa leçon.')
          : 'Image refusée : l\'enfant ne la verra pas.',
    );
  }

  Future<void> _approveAll(List<LessonImage> pictures) {
    final api = ref.read(apiProvider);
    final (child, lesson) = _ids;
    return _act(() async {
      for (final p in pictures) {
        await api.decidePicture(child, lesson, p.id!, approve: true);
      }
      return null;
    }, '${pictures.length} images validées : les jeux en images sont prêts.');
  }

  @override
  Widget build(BuildContext context) {
    final value = ref.watch(lessonImagesProvider(_ids)).value;
    if (value == null) return const SizedBox();
    _follow(value);
    final image = value.image;
    // Pas de moteur d'images et rien de préparé : la carte ne sert à rien.
    if (image == null && value.pictures.isEmpty && !value.available) return const SizedBox();
    final toReview = [
      for (final p in value.pictures)
        if (p.status == ImageStatus.toReview && p.id != null) p,
    ];
    final nothingYet = image == null && value.pictures.isEmpty;
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
            if (nothingYet) ...[
              const Text(
                'Pas d\'image pour cette leçon. Elle est facultative : les questions n\'en '
                'dépendent pas. L\'IA ne dessine que si une image aide à retenir la leçon.',
                style: TextStyle(fontSize: 14, color: Colors.black54),
              ),
              if (value.available) ...[
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    FilledButton.icon(
                      onPressed: _busy
                          ? null
                          : () => _act(
                              () => ref.read(apiProvider).prepareImages(_ids.$1, _ids.$2),
                              'Images demandées : l\'IA dit d\'abord si elles aident, puis elles '
                              'sont dessinées (quelques minutes).',
                            ),
                      icon: const Icon(Icons.auto_awesome),
                      label: const Text('Préparer les images'),
                    ),
                    OutlinedButton.icon(
                      onPressed: _busy ? null : () => _redo(null),
                      icon: const Icon(Icons.refresh),
                      label: const Text('Créer une image'),
                    ),
                  ],
                ),
              ],
            ] else ...[
              if (image != null)
                _ImageTile(
                  image: image,
                  available: value.available,
                  busy: _busy,
                  onDecide: (approve) => _decide(image, approve: approve),
                  onRedo: () => _redo(image),
                ),
              if (value.pictures.isNotEmpty) ...[
                const Divider(height: 28),
                Text('Images pour apprendre', style: Theme.of(context).textTheme.titleSmall),
                const SizedBox(height: 4),
                const Text(
                  'Une image par notion : validées, elles s\'affichent avec la notion et servent '
                  'aux jeux « Image et mot » et « Quelle image ? » (trois au moins). Vérifiez que '
                  'chacune montre bien sa notion.',
                  style: TextStyle(fontSize: 14, color: Colors.black54),
                ),
                if (toReview.length > 1) ...[
                  const SizedBox(height: 8),
                  FilledButton.tonalIcon(
                    onPressed: _busy ? null : () => _approveAll(toReview),
                    icon: const Icon(Icons.done_all),
                    label: Text('Valider les ${toReview.length} images'),
                  ),
                ],
                for (final picture in value.pictures) ...[
                  const SizedBox(height: 16),
                  _ImageTile(
                    image: picture,
                    available: value.available,
                    busy: _busy,
                    onDecide: (approve) => _decide(picture, approve: approve),
                    onRedo: () => _redo(picture),
                  ),
                ],
              ],
            ],
          ],
        ),
      ),
    );
  }
}

/// Une image, son état et ses boutons (valider, refuser, refaire).
class _ImageTile extends StatelessWidget {
  const _ImageTile({
    required this.image,
    required this.available,
    required this.busy,
    required this.onDecide,
    required this.onRedo,
  });

  final LessonImage image;
  final bool available;
  final bool busy;
  final ValueChanged<bool> onDecide;
  final VoidCallback onRedo;

  @override
  Widget build(BuildContext context) {
    final ready = image.url != null;
    final status = image.status;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (image.label case final label?)
          Text(label, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
        Text(_statusText(image), style: const TextStyle(fontSize: 14, color: Colors.black54)),
        if (image.url case final url?) ...[
          const SizedBox(height: 12),
          ClipRRect(
            borderRadius: BorderRadius.circular(12),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 320),
              child: ApiImage(
                url,
                semanticLabel: image.alt,
                fit: BoxFit.contain,
                fallback: const Text('Image indisponible pour le moment.'),
              ),
            ),
          ),
        ],
        if (image.alt case final alt? when ready) ...[
          const SizedBox(height: 6),
          Text(alt, style: const TextStyle(fontSize: 14, fontStyle: FontStyle.italic)),
        ],
        if (image.exact && ready)
          const Text(
            '📐 Figure exacte dessinée par Ludifun (mesures et codage justes).',
            style: TextStyle(fontSize: 13, color: Colors.black54),
          ),
        if (image.remark case final remark?) ...[
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
            if (ready && status != ImageStatus.approved && status != ImageStatus.generating)
              FilledButton.icon(
                onPressed: busy ? null : () => onDecide(true),
                icon: const Icon(Icons.check),
                label: const Text('Valider'),
              ),
            if (ready && (status == ImageStatus.toReview || status == ImageStatus.approved))
              OutlinedButton.icon(
                onPressed: busy ? null : () => onDecide(false),
                icon: const Icon(Icons.close),
                label: const Text('Refuser'),
              ),
            if (available && status != ImageStatus.generating)
              OutlinedButton.icon(
                onPressed: busy ? null : onRedo,
                icon: const Icon(Icons.refresh),
                label: Text(status == ImageStatus.notNeeded ? 'Créer quand même' : 'Refaire'),
              ),
          ],
        ),
      ],
    );
  }
}

String _statusText(LessonImage image) {
  final notion = image.knowledgeId != null;
  return switch (image.status) {
    ImageStatus.generating => 'Image en préparation… (quelques minutes)',
    ImageStatus.toReview =>
      notion
          ? 'À valider : montre-t-elle bien la notion ? L\'enfant ne la verra qu\'après votre accord.'
          : 'À valider : l\'enfant ne la verra qu\'après votre accord. Elle est facultative.',
    ImageStatus.approved =>
      notion
          ? 'Validée : l\'enfant la voit avec la notion et dans les jeux en images.'
          : 'Validée : l\'enfant la voit avec sa leçon.',
    ImageStatus.rejected =>
      'Refusée : l\'enfant ne la voit pas. Vous pouvez demander de la refaire.',
    ImageStatus.notNeeded =>
      'Pas utile pour cette leçon${image.error == null ? '' : ' : ${image.error}'}. '
          'Vous pouvez en demander une quand même.',
    ImageStatus.failed =>
      'L\'image n\'a pas pu être faite${image.error == null ? '' : ' (${image.error})'}. '
          'La leçon, elle, est complète.',
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
        const Text(
          'Pour une figure de géométrie, nommez-la (« un carré », « un triangle rectangle ») : '
          'Ludifun la dessine exactement, avec son codage.',
          style: TextStyle(fontSize: 13, color: Colors.black54),
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
