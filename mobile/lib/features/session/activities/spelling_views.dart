import 'dart:async';

import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Phrase d'aide où le mot est remplacé par « ___ ».
class _Sentence extends StatelessWidget {
  const _Sentence(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 8),
    child: Text('💡 $text', style: const TextStyle(fontSize: 18, height: 1.3)),
  );
}

/// Mot éclair : `{prompt, word, show_ms, sentence?}` → `{text}`.
///
/// Le mot s'affiche quelques secondes (ou jusqu'à « Je l'ai retenu »), puis se cache :
/// l'enfant l'écrit de mémoire, comme la copie flash de la classe.
class WordFlashView extends StatefulWidget {
  const WordFlashView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<WordFlashView> createState() => _WordFlashViewState();
}

class _WordFlashViewState extends State<WordFlashView> {
  final _answer = TextEditingController();
  Timer? _timer;
  bool _hidden = false;
  bool _sent = false;

  Duration get _showFor =>
      Duration(milliseconds: (widget.payload['show_ms'] as num?)?.toInt() ?? 4000);

  @override
  void initState() {
    super.initState();
    _timer = Timer(_showFor, _hide);
  }

  @override
  void dispose() {
    _timer?.cancel();
    _answer.dispose();
    super.dispose();
  }

  void _hide() {
    _timer?.cancel();
    if (mounted && !_hidden) setState(() => _hidden = true);
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
          widget.payload['prompt'] as String? ?? 'Regarde le mot, puis écris-le.',
          label: '⚡ Mot éclair',
        ),
        const SizedBox(height: 8),
        Text(
          ActivityInstruction.of(context) ?? 'Mémorise le mot, puis écris-le sans le voir.',
          style: const TextStyle(fontSize: 16, color: Colors.black54),
        ),
        const SizedBox(height: 24),
        if (!_hidden) ...[
          Container(
            padding: const EdgeInsets.symmetric(vertical: 28, horizontal: 12),
            decoration: BoxDecoration(
              color: LudiColors.primary.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(18),
            ),
            child: Text(
              widget.payload['word'] as String,
              textAlign: TextAlign.center,
              style: const TextStyle(fontSize: 40, fontWeight: FontWeight.w800, letterSpacing: 2),
            ),
          ),
          const SizedBox(height: 12),
          TweenAnimationBuilder<double>(
            tween: Tween(begin: 1, end: 0),
            duration: _showFor,
            builder: (_, value, _) => LinearProgressIndicator(value: value, minHeight: 8),
          ),
          const SizedBox(height: 16),
          OutlinedButton(onPressed: _hide, child: const Text('Je l\'ai retenu')),
        ] else ...[
          if (sentence != null) _Sentence(sentence),
          const SizedBox(height: 16),
          TextField(
            controller: _answer,
            autofocus: true,
            enabled: !_sent,
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
      ],
    );
  }
}

/// Lettres mélangées : `{prompt, letters:[{id,text}], sentence?}` → `{order:[id…]}`.
///
/// L'enfant touche les lettres dans l'ordre ; toucher une lettre placée la retire.
class ScrambleView extends StatefulWidget {
  const ScrambleView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<ScrambleView> createState() => _ScrambleViewState();
}

class _ScrambleViewState extends State<ScrambleView> {
  late final List<Choice> _letters = choicesOf(widget.payload['letters']);
  final _order = <String>[];
  bool _sent = false;

  String _text(String id) => _letters.firstWhere((c) => c.id == id).text;

  void _toggle(String id) {
    if (_sent) return;
    setState(() => _order.contains(id) ? _order.remove(id) : _order.add(id));
  }

  void _submit() {
    if (_sent) return;
    setState(() => _sent = true);
    widget.onSubmit({'order': List.of(_order)});
  }

  @override
  Widget build(BuildContext context) {
    final left = _letters.where((c) => !_order.contains(c.id)).toList();
    final sentence = widget.payload['sentence'] as String?;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Prompt(
          widget.payload['prompt'] as String? ?? 'Remets les lettres dans l\'ordre.',
          label: '🔤 Lettres mélangées',
        ),
        const SizedBox(height: 8),
        Text(
          ActivityInstruction.of(context) ?? 'Touche les lettres dans l\'ordre pour écrire le mot.',
          style: const TextStyle(fontSize: 16, color: Colors.black54),
        ),
        if (sentence != null) _Sentence(sentence),
        const SizedBox(height: 20),
        // Le mot en cours : chaque lettre placée se retire en la touchant.
        Container(
          constraints: const BoxConstraints(minHeight: 64),
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: LudiColors.primary, width: 3)),
          ),
          child: Wrap(
            alignment: WrapAlignment.center,
            spacing: 6,
            runSpacing: 6,
            children: [
              for (final id in _order)
                _Tile(
                  letter: _text(id),
                  placed: true,
                  onTap: () => _toggle(id),
                  semantics: 'Lettre ${_text(id)} placée. Toucher pour retirer.',
                ),
            ],
          ),
        ),
        const SizedBox(height: 24),
        Wrap(
          alignment: WrapAlignment.center,
          spacing: 10,
          runSpacing: 10,
          children: [
            for (final choice in left)
              _Tile(
                letter: choice.text,
                placed: false,
                onTap: () => _toggle(choice.id),
                semantics: 'Lettre ${choice.text}',
              ),
          ],
        ),
        const SizedBox(height: 24),
        FilledButton(
          onPressed: left.isEmpty && !_sent ? _submit : null,
          child: Text(left.isEmpty ? 'Valider' : 'Encore ${left.length} lettre(s)'),
        ),
      ],
    );
  }
}

class _Tile extends StatelessWidget {
  const _Tile({
    required this.letter,
    required this.placed,
    required this.onTap,
    required this.semantics,
  });

  final String letter;
  final bool placed;
  final VoidCallback onTap;
  final String semantics;

  @override
  Widget build(BuildContext context) => Semantics(
    button: true,
    label: semantics,
    excludeSemantics: true,
    child: Material(
      color: placed ? LudiColors.primary : LudiColors.accent.withValues(alpha: 0.15),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: placed ? LudiColors.primary : LudiColors.accent, width: 2),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: SizedBox(
          width: 48,
          height: 56,
          child: Center(
            child: Text(
              letter,
              style: TextStyle(
                fontSize: 28,
                fontWeight: FontWeight.w800,
                color: placed ? Colors.white : Colors.black87,
              ),
            ),
          ),
        ),
      ),
    ),
  );
}
