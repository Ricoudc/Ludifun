import 'package:flutter/material.dart';

import '../../../app/theme.dart';
import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

const blank = '___';

/// Texte à trou : `{text: "… ___ …", hint?}` → `{text}`.
class FillBlankView extends StatefulWidget {
  const FillBlankView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<FillBlankView> createState() => _FillBlankViewState();
}

class _FillBlankViewState extends State<FillBlankView> {
  final _answer = TextEditingController();
  bool _sent = false;

  @override
  void dispose() {
    _answer.dispose();
    super.dispose();
  }

  void _submit() {
    final text = _answer.text.trim();
    if (text.isEmpty || _sent) return;
    setState(() => _sent = true);
    widget.onSubmit({'text': text});
  }

  @override
  Widget build(BuildContext context) {
    final text = widget.payload['text'] as String;
    final cut = text.indexOf(blank);
    final (before, after) = cut < 0
        ? (text, '')
        : (text.substring(0, cut), text.substring(cut + blank.length));
    final typed = _answer.text.trim();
    final style = Theme.of(context).textTheme.headlineSmall
        ?.copyWith(fontWeight: FontWeight.w600, height: 1.4);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          ActivityInstruction.of(context) ?? 'Complète la phrase',
          style: Theme.of(context).textTheme.labelLarge?.copyWith(color: LudiColors.primary),
        ),
        const SizedBox(height: 8),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Expanded(
              child: Text.rich(
                TextSpan(
                  style: style,
                  children: [
                    TextSpan(text: before),
                    TextSpan(
                      text: typed.isEmpty ? ' ______ ' : ' $typed ',
                      style: const TextStyle(
                        color: LudiColors.primary,
                        decoration: TextDecoration.underline,
                        decorationThickness: 2,
                      ),
                    ),
                    TextSpan(text: after),
                  ],
                ),
              ),
            ),
            ListenButton([ActivityInstruction.of(context) ?? 'Complète la phrase', text]),
          ],
        ),
        if (widget.payload['hint'] case final String hint) ...[
          const SizedBox(height: 8),
          Text('💡 $hint', style: const TextStyle(fontSize: 16)),
        ],
        const SizedBox(height: 24),
        TextField(
          controller: _answer,
          autofocus: true,
          enabled: !_sent,
          textInputAction: TextInputAction.done,
          style: const TextStyle(fontSize: 22),
          decoration: const InputDecoration(hintText: 'Ta réponse'),
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
