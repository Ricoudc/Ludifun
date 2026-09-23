import 'package:flutter/material.dart';

import '../api/models.dart';

/// QCM et vrai/faux.
class ChoiceQuestion extends StatelessWidget {
  final QuizQuestion question;
  final bool enabled;
  final ValueChanged<String> onAnswer;
  const ChoiceQuestion({super.key, required this.question, required this.enabled, required this.onAnswer});

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final choice in question.choices)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: OutlinedButton(
              onPressed: enabled ? () => onAnswer(choice) : null,
              child: Padding(padding: const EdgeInsets.all(12), child: Text(choice)),
            ),
          ),
      ],
    );
  }
}

/// Texte à trous et question ouverte (« Explique-moi »).
class TextQuestion extends StatefulWidget {
  final QuizQuestion question;
  final bool enabled;
  final bool multiline;
  final ValueChanged<String> onAnswer;
  const TextQuestion(
      {super.key, required this.question, required this.enabled, required this.onAnswer, this.multiline = false});

  @override
  State<TextQuestion> createState() => _TextQuestionState();
}

class _TextQuestionState extends State<TextQuestion> {
  final _controller = TextEditingController();

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      TextField(
        controller: _controller,
        enabled: widget.enabled,
        minLines: widget.multiline ? 3 : 1,
        maxLines: widget.multiline ? 6 : 1,
        decoration: InputDecoration(
          border: const OutlineInputBorder(),
          hintText: widget.multiline ? 'Explique avec tes propres mots…' : 'Ta réponse',
        ),
        onSubmitted: widget.multiline ? null : widget.onAnswer,
      ),
      const SizedBox(height: 8),
      FilledButton(
        onPressed: widget.enabled ? () => widget.onAnswer(_controller.text) : null,
        child: const Text('Valider'),
      ),
    ]);
  }
}

/// Carte mémoire : l'enfant retourne la carte puis dit s'il savait.
class FlashcardQuestion extends StatefulWidget {
  final QuizQuestion question;
  final bool enabled;
  final ValueChanged<String> onAnswer;
  const FlashcardQuestion({super.key, required this.question, required this.enabled, required this.onAnswer});

  @override
  State<FlashcardQuestion> createState() => _FlashcardQuestionState();
}

class _FlashcardQuestionState extends State<FlashcardQuestion> {
  bool _flipped = false;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      GestureDetector(
        onTap: () => setState(() => _flipped = true),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          height: 180,
          padding: const EdgeInsets.all(16),
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: _flipped ? scheme.secondaryContainer : scheme.primaryContainer,
            borderRadius: BorderRadius.circular(16),
          ),
          child: Text(
            _flipped ? (widget.question.back ?? '') : '👆 Touche pour retourner la carte',
            textAlign: TextAlign.center,
            style: const TextStyle(fontSize: 18),
          ),
        ),
      ),
      if (_flipped) ...[
        const SizedBox(height: 12),
        Row(children: [
          Expanded(
            child: OutlinedButton(
              onPressed: widget.enabled ? () => widget.onAnswer('je ne savais pas') : null,
              child: const Text('😕 Je ne savais pas'),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: FilledButton(
              onPressed: widget.enabled ? () => widget.onAnswer('je savais') : null,
              child: const Text('😀 Je savais'),
            ),
          ),
        ]),
      ],
    ]);
  }
}

/// Association : pour chaque élément de gauche, choisir l'élément de droite.
class MatchingQuestion extends StatefulWidget {
  final QuizQuestion question;
  final bool enabled;
  final ValueChanged<Map<String, String>> onAnswer;
  const MatchingQuestion({super.key, required this.question, required this.enabled, required this.onAnswer});

  @override
  State<MatchingQuestion> createState() => _MatchingQuestionState();
}

class _MatchingQuestionState extends State<MatchingQuestion> {
  final _matches = <String, String>{};

  @override
  Widget build(BuildContext context) {
    final q = widget.question;
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      for (final left in q.leftItems)
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(children: [
            Expanded(child: Text(left, style: const TextStyle(fontWeight: FontWeight.bold))),
            const Icon(Icons.arrow_forward),
            const SizedBox(width: 8),
            Expanded(
              child: DropdownButton<String>(
                isExpanded: true,
                hint: const Text('Choisis'),
                value: _matches[left],
                items: [for (final r in q.rightItems) DropdownMenuItem(value: r, child: Text(r))],
                onChanged: widget.enabled ? (v) => setState(() => _matches[left] = v!) : null,
              ),
            ),
          ]),
        ),
      FilledButton(
        onPressed: widget.enabled && _matches.length == q.leftItems.length ? () => widget.onAnswer(_matches) : null,
        child: const Text('Valider'),
      ),
    ]);
  }
}

class FeedbackCard extends StatelessWidget {
  final AnswerResult result;
  const FeedbackCard({super.key, required this.result});

  @override
  Widget build(BuildContext context) {
    final ok = result.correct;
    return Card(
      color: ok ? Colors.green.shade50 : Colors.orange.shade50,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(ok ? '✅ Bonne réponse !' : '🤔 Pas tout à fait…',
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          Text(result.feedback),
          if (!ok) ...[
            const SizedBox(height: 8),
            Text('La réponse : ${result.expected}', style: const TextStyle(fontStyle: FontStyle.italic)),
          ],
          if (result.missingPoints.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text('Il te manque : ${result.missingPoints.join(', ')}'),
          ],
        ]),
      ),
    );
  }
}
