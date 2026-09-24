import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../home/home_providers.dart';
import 'capture_controller.dart';

/// Écran 2 : une à six pages, réordonnables, compressées sur le téléphone puis envoyées.
/// Avec [childId], c'est le parent qui photographie une leçon pour son enfant (écran P3).
class CaptureScreen extends ConsumerStatefulWidget {
  const CaptureScreen({this.childId, super.key});

  final String? childId;

  @override
  ConsumerState<CaptureScreen> createState() => _CaptureScreenState();
}

class _CaptureScreenState extends ConsumerState<CaptureScreen> {
  double? _progress; // envoi en cours
  String? _error;

  Future<void> _pick(Future<void> Function() pick) async {
    setState(() => _error = null);
    try {
      await pick();
    } on Exception {
      setState(() => _error = 'Impossible d\'ouvrir les photos. Vérifie les autorisations.');
    }
  }

  Future<void> _analyze() async {
    setState(() {
      _progress = 0;
      _error = null;
    });
    try {
      final pages = await ref.read(captureProvider.notifier).compressed();
      final lesson = await ref
          .read(apiProvider)
          .uploadLesson(
            pages,
            childId: widget.childId,
            onProgress: (sent, total) {
              if (mounted && total > 0) setState(() => _progress = sent / total);
            },
          );
      ref.read(captureProvider.notifier).markSent(lesson.id);
      refreshHome(ref);
      if (mounted) context.go(Routes.analysis(lesson.id, childId: widget.childId));
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _progress = null;
          _error = error.message;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final pages = ref.watch(captureProvider);
    final capture = ref.read(captureProvider.notifier);
    final sending = _progress != null;
    final full = pages.length >= maxPages;
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(
          onPressed: () => context.go(
            widget.childId == null ? Routes.childHome : Routes.childDashboard(widget.childId!),
          ),
        ),
        title: Text(
          widget.childId == null ? '📷 Photographie ta leçon' : '📷 Photographier la leçon',
        ),
      ),
      body: CenteredBody(
        top: true,
        children: [
          FilledButton.icon(
            onPressed: sending || full ? null : () => _pick(capture.takePhoto),
            icon: const Icon(Icons.photo_camera),
            label: const Text('Prendre une photo'),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: sending || full ? null : () => _pick(capture.pickFromGallery),
            icon: const Icon(Icons.photo_library_outlined),
            label: const Text('Ajouter depuis la galerie'),
          ),
          const SizedBox(height: 4),
          TextButton.icon(
            onPressed: sending
                ? null
                : () => context.go(
                    widget.childId == null ? Routes.paste : Routes.childPaste(widget.childId!),
                  ),
            icon: const Icon(Icons.content_paste),
            label: const Text('J\'ai le texte de la leçon'),
          ),
          const SizedBox(height: 12),
          if (pages.isEmpty)
            const _Tip()
          else ...[
            Text(
              full
                  ? '$maxPages pages : c\'est le maximum.'
                  : 'Tu peux ajouter plusieurs pages. Glisse-les pour changer l\'ordre.',
            ),
            const SizedBox(height: 12),
            SizedBox(
              height: 190,
              child: ReorderableListView.builder(
                scrollDirection: Axis.horizontal,
                buildDefaultDragHandles: !sending,
                itemCount: pages.length,
                onReorderItem: capture.move,
                itemBuilder: (context, i) => _Thumbnail(
                  key: ObjectKey(pages[i]),
                  index: i,
                  page: pages[i],
                  onRemove: sending ? null : () => capture.remove(i),
                ),
              ),
            ),
          ],
          if (_error != null) ...[const SizedBox(height: 16), ErrorMessage(_error!)],
          const SizedBox(height: 24),
          if (sending) ...[
            LinearProgressIndicator(value: _progress == 0 ? null : _progress),
            const SizedBox(height: 8),
            const Text('Envoi de ta leçon…', textAlign: TextAlign.center),
          ] else
            FilledButton(
              onPressed: pages.isEmpty ? null : _analyze,
              style: FilledButton.styleFrom(backgroundColor: LudiColors.accent),
              child: const Text('Analyser ma leçon'),
            ),
        ],
      ),
    );
  }
}

class _Tip extends StatelessWidget {
  const _Tip();

  @override
  Widget build(BuildContext context) => const Card(
    child: Padding(
      padding: EdgeInsets.all(20),
      child: Row(
        children: [
          Text('💡', style: TextStyle(fontSize: 32)),
          SizedBox(width: 12),
          Expanded(
            child: Text(
              'Pose le cahier à plat, avec de la lumière.',
              style: TextStyle(fontSize: 18),
            ),
          ),
        ],
      ),
    ),
  );
}

class _Thumbnail extends StatelessWidget {
  const _Thumbnail({required this.index, required this.page, this.onRemove, super.key});

  final int index;
  final CapturedPage page;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(right: 12),
    child: Stack(
      children: [
        ClipRRect(
          borderRadius: BorderRadius.circular(12),
          child: Image.memory(
            page.bytes,
            width: 130,
            height: 190,
            fit: BoxFit.cover,
            cacheWidth: 260,
            semanticLabel: 'Page ${index + 1}',
          ),
        ),
        Positioned(
          left: 6,
          bottom: 6,
          child: CircleAvatar(radius: 14, child: Text('${index + 1}')),
        ),
        if (onRemove != null)
          Positioned(
            right: 2,
            top: 2,
            child: IconButton.filled(
              tooltip: 'Retirer la page ${index + 1}',
              style: IconButton.styleFrom(backgroundColor: Colors.black54),
              iconSize: 18,
              onPressed: onRemove,
              icon: const Icon(Icons.close),
            ),
          ),
      ],
    ),
  );
}
