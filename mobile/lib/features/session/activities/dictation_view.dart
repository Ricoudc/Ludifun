import 'dart:async';

import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../core/speech.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Dictée : `{prompt, word, sentence?, spoken_sentence?}` → `{text}`.
///
/// Le téléphone lit le mot, la phrase qui l'emploie, puis le mot encore ; l'enfant l'écrit
/// sans l'avoir vu (le mot n'est jamais affiché). Sans voix française sur le téléphone, le
/// mot s'affiche trois secondes à la place, comme un mot éclair.
class DictationView extends StatefulWidget {
  const DictationView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  /// Remplacé dans les tests.
  static Speaker Function() speakerFactory = PhoneSpeaker.new;

  @override
  State<DictationView> createState() => _DictationViewState();
}

class _DictationViewState extends State<DictationView> {
  late final Speaker _speaker = DictationView.speakerFactory();
  final _answer = TextEditingController();
  bool _speaking = false;
  bool _noVoice = false;
  bool _showWord = false;
  bool _sent = false;
  Timer? _hide;

  String get _word => widget.payload['word'] as String;

  @override
  void initState() {
    super.initState();
    unawaited(_listen());
  }

  @override
  void dispose() {
    _hide?.cancel();
    unawaited(_speaker.stop());
    _answer.dispose();
    super.dispose();
  }

  Future<void> _listen() async {
    if (_speaking) return;
    setState(() => _speaking = true);
    final spoken = widget.payload['spoken_sentence'] as String?;
    var ok = await _speaker.speak(_word);
    if (ok && spoken != null) ok = await _speaker.speak(spoken);
    if (ok) ok = await _speaker.speak(_word);
    if (!mounted) return;
    setState(() {
      _speaking = false;
      if (!ok) {
        _noVoice = true;
        _showWord = true;
        _hide = Timer(const Duration(seconds: 3), () {
          if (mounted) setState(() => _showWord = false);
        });
      }
    });
  }

  void _submit() {
    final text = _answer.text.trim();
    if (text.isEmpty || _sent) return;
    setState(() => _sent = true);
    widget.onSubmit({'text': text});
  }

  @override
  Widget build(BuildContext context) {
    final sentence = widget.payload['sentence'] as String?;
    final typed = _answer.text.trim();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(
          widget.payload['prompt'] as String? ?? 'Écoute le mot, puis écris-le.',
          label: '🎧 Dictée',
        ),
        const SizedBox(height: 8),
        Text(
          ActivityInstruction.of(context) ?? 'Écoute le mot, puis écris-le.',
          style: const TextStyle(fontSize: 16, color: Colors.black54),
        ),
        const SizedBox(height: 20),
        if (_noVoice)
          Text(
            _showWord
                ? _word
                : 'Le téléphone ne sait pas lire à voix haute : le mot s\'est affiché.',
            textAlign: TextAlign.center,
            style: _showWord
                ? const TextStyle(fontSize: 36, fontWeight: FontWeight.w800)
                : const TextStyle(fontSize: 14, color: Colors.black54),
          )
        else
          Center(
            child: FilledButton.tonalIcon(
              onPressed: _speaking || _sent ? null : _listen,
              icon: Icon(_speaking ? Icons.graphic_eq : Icons.volume_up, size: 32),
              label: Text(_speaking ? 'J\'écoute…' : 'Réécouter'),
            ),
          ),
        if (sentence != null) ...[
          const SizedBox(height: 12),
          Text(
            '💡 $sentence',
            style: const TextStyle(fontSize: 18, height: 1.3, color: LudiColors.primary),
          ),
        ],
        const SizedBox(height: 16),
        TextField(
          controller: _answer,
          enabled: !_sent && !_showWord,
          autocorrect: false,
          enableSuggestions: false,
          textInputAction: TextInputAction.done,
          style: const TextStyle(fontSize: 26),
          decoration: const InputDecoration(hintText: 'Écris le mot'),
          onChanged: (_) => setState(() {}),
          onSubmitted: (_) => _submit(),
        ),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: typed.isEmpty || _sent ? null : _submit,
          child: const Text('Valider'),
        ),
      ],
    );
  }
}
