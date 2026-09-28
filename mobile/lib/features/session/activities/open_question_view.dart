import 'package:flutter/material.dart';

import '../../../models/account.dart';
import 'activity_registry.dart';
import 'common.dart';

/// Question ouverte : `{prompt, max_length}` → `{text}`. L'enfant répond avec ses mots ;
/// la correction (quelques secondes) dit quels points clés sont présents.
class OpenQuestionView extends StatefulWidget {
  const OpenQuestionView({required this.payload, required this.onSubmit, super.key});

  final Json payload;
  final ActivitySubmit onSubmit;

  @override
  State<OpenQuestionView> createState() => _OpenQuestionViewState();
}

class _OpenQuestionViewState extends State<OpenQuestionView> {
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
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Prompt(
        widget.payload['prompt'] as String,
        label: ActivityInstruction.of(context) ?? 'Réponds avec tes mots',
      ),
      const SizedBox(height: 20),
      TextField(
        controller: _answer,
        enabled: !_sent,
        minLines: 3,
        maxLines: 6,
        maxLength: widget.payload['max_length'] as int? ?? 600,
        textCapitalization: TextCapitalization.sentences,
        style: const TextStyle(fontSize: 19),
        decoration: const InputDecoration(
          hintText: 'Écris ta réponse en une ou deux phrases',
          border: OutlineInputBorder(),
        ),
        onChanged: (_) => setState(() {}),
      ),
      const SizedBox(height: 12),
      FilledButton(
        onPressed: _answer.text.trim().isEmpty || _sent ? null : _submit,
        child: Text(_sent ? 'Je lis ta réponse…' : 'Valider'),
      ),
    ],
  );
}
