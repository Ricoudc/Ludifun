import 'package:flutter/material.dart';

import '../../app/theme.dart';
import '../../models/account.dart';
import '../../models/session.dart';
import 'activities/activity_registry.dart';

/// Écran 6 : correction immédiate, jamais culpabilisante.
class CorrectionView extends StatelessWidget {
  const CorrectionView({
    required this.item,
    required this.correction,
    required this.onContinue,
    super.key,
  });

  final SessionItem item;
  final Correction correction;
  final VoidCallback onContinue;

  @override
  Widget build(BuildContext context) {
    final (title, color) = switch (correction.result) {
      AttemptResult.correct => ('✅ Bravo !', LudiColors.mastered),
      AttemptResult.partial => ('👍 Presque !', LudiColors.toReview),
      _ => ('❌ Pas tout à fait !', LudiColors.notMastered),
    };
    final openQuestion = item.type == 'OPEN_QUESTION';
    final details = openQuestion ? _keyPoints() : _details();
    final showAnswer =
        correction.result != AttemptResult.correct && (details.isEmpty || openQuestion);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(18),
            border: Border.all(color: color, width: 2),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: Theme.of(context).textTheme.headlineMedium
                    ?.copyWith(color: color, fontWeight: FontWeight.w800),
              ),
              if (showAnswer && openQuestion && correction.correctAnswer != null) ...[
                const SizedBox(height: 12),
                Text(
                  'Une réponse possible : ${correction.correctAnswer}',
                  style: const TextStyle(fontSize: 19),
                ),
              ] else if (showAnswer && correction.correctAnswer != null) ...[
                const SizedBox(height: 12),
                Text.rich(
                  TextSpan(
                    children: [
                      const TextSpan(text: 'La bonne réponse est '),
                      TextSpan(
                        text: correction.correctAnswer,
                        style: const TextStyle(fontWeight: FontWeight.w800),
                      ),
                      const TextSpan(text: '.'),
                    ],
                  ),
                  style: const TextStyle(fontSize: 20),
                ),
              ],
              if (item.type == 'SPEED_CHALLENGE' && correction.correctAnswer != null) ...[
                const SizedBox(height: 8),
                Text(correction.correctAnswer!, style: const TextStyle(fontSize: 18)),
              ],
            ],
          ),
        ),
        if (details.isNotEmpty) ...[const SizedBox(height: 16), ...details],
        if (correction.result != AttemptResult.correct && correction.tip != null) ...[
          const SizedBox(height: 16),
          Text('💡 Astuce pour retenir : ${correction.tip}', style: const TextStyle(fontSize: 18)),
        ],
        if (correction.explanation != null) ...[
          const SizedBox(height: 12),
          Text(correction.explanation!, style: const TextStyle(fontSize: 17, height: 1.35)),
        ],
        const SizedBox(height: 28),
        FilledButton(autofocus: true, onPressed: onContinue, child: const Text('Continuer')),
      ],
    );
  }

  /// Question ouverte : les points clés trouvés dans la réponse de l'enfant, et ceux qui manquent.
  List<Widget> _keyPoints() => [
    if (correction.details.isNotEmpty)
      const Padding(
        padding: EdgeInsets.only(bottom: 8),
        child: Text(
          'Ce qu\'on attendait :',
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.w700),
        ),
      ),
    for (final Json d in correction.details)
      Padding(
        padding: const EdgeInsets.only(bottom: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(
              d['found'] == true ? Icons.check_circle : Icons.radio_button_unchecked,
              color: d['found'] == true ? LudiColors.mastered : LudiColors.toReview,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                '${d['point']}${d['found'] == true ? '' : ' (il manquait)'}',
                style: const TextStyle(fontSize: 17),
              ),
            ),
          ],
        ),
      ),
  ];

  /// Association et défi rapide : le résultat élément par élément.
  List<Widget> _details() {
    if (correction.details.isEmpty) return const [];
    final texts = {
      for (final key in ['left', 'statements'])
        if (item.payload[key] != null)
          for (final c in choicesOf(item.payload[key])) c.id: c.text,
    };
    return [
      for (final Json d in correction.details)
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(
                d['correct'] == true ? Icons.check_circle : Icons.cancel,
                color: d['correct'] == true ? LudiColors.mastered : LudiColors.notMastered,
              ),
              const SizedBox(width: 10),
              Expanded(child: Text(_detailText(d, texts), style: const TextStyle(fontSize: 17))),
            ],
          ),
        ),
    ];
  }

  String _detailText(Json d, Map<String, String> texts) {
    final text = texts[d['id']] ?? '';
    return switch (d['expected']) {
      final String right => '$text → $right',
      final bool value when d['correct'] == true => '$text (${value ? 'vrai' : 'faux'})',
      final bool value =>
        '$text\nC\'était ${value ? 'vrai' : 'faux'}.'
            '${d['correction'] is String ? ' ${d['correction']}' : ''}',
      _ => text,
    };
  }
}
