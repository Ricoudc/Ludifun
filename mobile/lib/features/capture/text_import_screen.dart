import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../home/home_providers.dart';

/// Assez de texte pour une leçon (le serveur refuse en dessous).
const minLessonChars = 40;

/// Leçon collée ou tapée (cahier des charges complet §8.5) : un cours reçu par l'ENT, un
/// document numérique… Même analyse que pour une photo, sans l'étape de lecture.
class TextImportScreen extends ConsumerStatefulWidget {
  const TextImportScreen({this.childId, super.key});

  /// Leçon déposée par le parent pour cet enfant.
  final String? childId;

  @override
  ConsumerState<TextImportScreen> createState() => _TextImportScreenState();
}

class _TextImportScreenState extends ConsumerState<TextImportScreen> {
  final _text = TextEditingController();
  bool _sending = false;
  String? _error;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  Future<void> _paste() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final pasted = data?.text?.trim();
    if (pasted == null || pasted.isEmpty) return;
    setState(() => _text.text = pasted);
  }

  Future<void> _analyze() async {
    setState(() {
      _sending = true;
      _error = null;
    });
    try {
      final lesson = await ref
          .read(apiProvider)
          .lessonFromText(_text.text.trim(), childId: widget.childId);
      refreshHome(ref);
      if (mounted) context.go(Routes.analysis(lesson.id, childId: widget.childId));
    } on ApiException catch (error) {
      if (mounted) {
        setState(() {
          _sending = false;
          _error = error.message;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final length = _text.text.trim().length;
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(
          onPressed: () => context.go(
            widget.childId == null ? Routes.capture : Routes.childCapture(widget.childId!),
          ),
        ),
        title: const Text('📋 Coller une leçon'),
      ),
      body: CenteredBody(
        top: true,
        children: [
          const Text(
            'Colle ici le texte de ta leçon (un cours reçu par l\'ENT, un document…).',
            style: TextStyle(fontSize: 17),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: _sending ? null : _paste,
            icon: const Icon(Icons.content_paste),
            label: const Text('Coller'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _text,
            enabled: !_sending,
            minLines: 8,
            maxLines: 16,
            style: const TextStyle(fontSize: 17),
            decoration: const InputDecoration(
              hintText: 'Le texte de la leçon',
              border: OutlineInputBorder(),
            ),
            onChanged: (_) => setState(() {}),
          ),
          if (length > 0 && length < minLessonChars) ...[
            const SizedBox(height: 8),
            const Text(
              'C\'est un peu court pour une leçon.',
              style: TextStyle(color: Colors.black54),
            ),
          ],
          if (_error != null) ...[const SizedBox(height: 16), ErrorMessage(_error!)],
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _sending || length < minLessonChars ? null : _analyze,
            style: FilledButton.styleFrom(backgroundColor: LudiColors.accent),
            child: Text(_sending ? 'Envoi…' : 'Analyser ma leçon'),
          ),
        ],
      ),
    );
  }
}
