import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../home/home_providers.dart';

/// Au moins 3 mots pour une dictée (le serveur refuse en dessous).
const minDictationWords = 3;

/// Les lignes non vides : une estimation du nombre de mots (le serveur décide).
int typedWords(String text) {
  final lines = [
    for (final line in text.split('\n'))
      if (line.trim().isNotEmpty) line,
  ];
  if (lines.length == 1 && !lines.first.contains(':')) {
    return lines.first.split(RegExp('[,;]')).where((w) => w.trim().isNotEmpty).length;
  }
  return lines.length;
}

/// Dictée à partir d'une liste de mots (§5.99) : les mots de la semaine, un par ligne, avec s'il
/// le faut une phrase qui les emploie. Prête tout de suite, sans IA.
class WordListScreen extends ConsumerStatefulWidget {
  const WordListScreen({this.childId, super.key});

  /// Liste tapée par le parent pour cet enfant.
  final String? childId;

  @override
  ConsumerState<WordListScreen> createState() => _WordListScreenState();
}

class _WordListScreenState extends ConsumerState<WordListScreen> {
  final _title = TextEditingController();
  final _words = TextEditingController();
  bool _sending = false;
  String? _error;

  @override
  void dispose() {
    _title.dispose();
    _words.dispose();
    super.dispose();
  }

  Future<void> _create() async {
    setState(() {
      _sending = true;
      _error = null;
    });
    final title = _title.text.trim();
    try {
      final lesson = await ref
          .read(apiProvider)
          .lessonFromWords(
            _words.text.trim(),
            title: title.isEmpty ? null : title,
            childId: widget.childId,
          );
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
    final count = typedWords(_words.text);
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(
          onPressed: () => context.go(
            widget.childId == null ? Routes.capture : Routes.childCapture(widget.childId!),
          ),
        ),
        title: const Text('✏️ Liste de mots'),
      ),
      body: CenteredBody(
        top: true,
        children: [
          const Text(
            'Écris les mots à savoir écrire, un par ligne. Ludifun prépare la dictée tout de '
            'suite : mot éclair, lettres mélangées, dictée du mot.',
            style: TextStyle(fontSize: 17),
          ),
          const SizedBox(height: 8),
          const Text(
            'Pour dicter aussi une phrase : « chaton : Le chaton dort sur le lit. »',
            style: TextStyle(fontSize: 15, color: Colors.black54),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _title,
            enabled: !_sending,
            style: const TextStyle(fontSize: 17),
            decoration: const InputDecoration(
              labelText: 'Titre (facultatif)',
              hintText: 'Mots de la semaine',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            key: const ValueKey('words'),
            controller: _words,
            enabled: !_sending,
            minLines: 8,
            maxLines: 16,
            style: const TextStyle(fontSize: 17),
            decoration: const InputDecoration(
              hintText: 'chaton\nmaison\nécole : Je vais à l\'école.',
              border: OutlineInputBorder(),
            ),
            onChanged: (_) => setState(() {}),
          ),
          const SizedBox(height: 8),
          Text(
            count < minDictationWords
                ? 'Au moins $minDictationWords mots.'
                : '$count mots dans la dictée.',
            style: const TextStyle(color: Colors.black54),
          ),
          if (_error != null) ...[const SizedBox(height: 16), ErrorMessage(_error!)],
          const SizedBox(height: 20),
          FilledButton(
            onPressed: _sending || count < minDictationWords ? null : _create,
            style: FilledButton.styleFrom(backgroundColor: LudiColors.accent),
            child: Text(_sending ? 'Préparation…' : 'Créer la dictée'),
          ),
        ],
      ),
    );
  }
}
