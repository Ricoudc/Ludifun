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
          listen: false,
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

/// Dictée de phrases (§5.64) : `{prompt, sentence, chunks, word_count, show_ms}` → `{text}`.
///
/// Comme en classe : le téléphone lit la phrase, puis morceau par morceau, puis encore en
/// entier ; l'enfant l'écrit sans l'avoir vue. Il peut réécouter la phrase ou les morceaux.
/// Sans voix française sur le téléphone, la phrase s'affiche `show_ms` millisecondes.
class SentenceDictationView extends StatefulWidget {
  const SentenceDictationView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<SentenceDictationView> createState() => _SentenceDictationViewState();
}

class _SentenceDictationViewState extends State<SentenceDictationView> {
  late final Speaker _speaker = DictationView.speakerFactory();
  final _answer = TextEditingController();
  bool _speaking = false;
  bool _noVoice = false;
  bool _showSentence = false;
  bool _sent = false;
  Timer? _hide;

  String get _sentence => widget.payload['sentence'] as String;

  List<String> get _chunks => [
    for (final chunk in widget.payload['chunks'] as List<dynamic>? ?? const []) chunk as String,
  ];

  @override
  void initState() {
    super.initState();
    unawaited(_read([_sentence, ..._chunks, _sentence]));
  }

  @override
  void dispose() {
    _hide?.cancel();
    unawaited(_speaker.stop());
    _answer.dispose();
    super.dispose();
  }

  Future<void> _read(List<String> texts) async {
    if (_speaking) return;
    setState(() => _speaking = true);
    var ok = true;
    for (final text in texts) {
      ok = await _speaker.speak(text);
      if (!ok || !mounted) break;
    }
    if (!mounted) return;
    setState(() {
      _speaking = false;
      if (!ok) {
        _noVoice = true;
        _showSentence = true;
        final ms = widget.payload['show_ms'] as int? ?? 5000;
        _hide = Timer(Duration(milliseconds: ms), () {
          if (mounted) setState(() => _showSentence = false);
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
    final count = widget.payload['word_count'] as int?;
    final typed = _answer.text.trim();
    final idle = !_speaking && !_sent;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(
          widget.payload['prompt'] as String? ?? 'Écoute la phrase, puis écris-la.',
          label: '🎧 Dictée de phrase',
          listen: false,
        ),
        const SizedBox(height: 8),
        Text(
          ActivityInstruction.of(context) ?? 'Écoute la phrase, puis écris-la.',
          style: const TextStyle(fontSize: 16, color: Colors.black54),
        ),
        const SizedBox(height: 20),
        if (_noVoice)
          Text(
            _showSentence
                ? _sentence
                : 'Le téléphone ne sait pas lire à voix haute : la phrase s\'est affichée.',
            textAlign: TextAlign.center,
            style: _showSentence
                ? const TextStyle(fontSize: 26, fontWeight: FontWeight.w800, height: 1.3)
                : const TextStyle(fontSize: 14, color: Colors.black54),
          )
        else
          Wrap(
            alignment: WrapAlignment.center,
            spacing: 12,
            runSpacing: 12,
            children: [
              FilledButton.tonalIcon(
                onPressed: idle ? () => _read([_sentence]) : null,
                icon: Icon(_speaking ? Icons.graphic_eq : Icons.volume_up, size: 28),
                label: Text(_speaking ? 'J\'écoute…' : 'Toute la phrase'),
              ),
              if (_chunks.length > 1)
                OutlinedButton.icon(
                  onPressed: idle ? () => _read(_chunks) : null,
                  icon: const Icon(Icons.slow_motion_video),
                  label: const Text('Morceau par morceau'),
                ),
            ],
          ),
        if (count != null) ...[
          const SizedBox(height: 12),
          Text(
            'La phrase a $count mots.',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 17, color: LudiColors.primary),
          ),
        ],
        const SizedBox(height: 16),
        TextField(
          controller: _answer,
          enabled: !_sent && !_showSentence,
          autocorrect: false,
          enableSuggestions: false,
          textCapitalization: TextCapitalization.sentences,
          minLines: 2,
          maxLines: 4,
          style: const TextStyle(fontSize: 22),
          decoration: const InputDecoration(hintText: 'Écris la phrase'),
          onChanged: (_) => setState(() {}),
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
