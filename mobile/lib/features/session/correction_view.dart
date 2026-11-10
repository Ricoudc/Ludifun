import 'package:flutter/material.dart';

import '../../app/api_image.dart';
import '../../app/theme.dart';
import '../../models/account.dart';
import '../../models/figure.dart';
import '../../models/session.dart';
import 'activities/activity_registry.dart';
import 'activities/figure_canvas.dart';
import 'cheers.dart';

/// Écran 6 : correction immédiate, jamais culpabilisante.
class CorrectionView extends StatelessWidget {
  const CorrectionView({
    required this.item,
    required this.correction,
    required this.onContinue,
    this.onPause,
    this.report,
    this.stars,
    this.streak = 0,
    this.onStar,
    this.showContinueButton = true,
    super.key,
  });

  final SessionItem item;
  final Correction correction;
  final VoidCallback onContinue;

  /// « Faire une pause » : la séance reste reprenable depuis l'accueil.
  final VoidCallback? onPause;

  /// « 🚩 Signaler un problème » (absent dans les tests des jeux seuls).
  final Widget? report;

  /// Étoiles gagnées par ce jeu (0 à 3) ; absentes : pas d'étoiles montrées.
  final int? stars;

  /// Bonnes réponses d'affilée, celle-ci comprise.
  final int streak;

  /// Chaque étoile qui apparaît (petit son).
  final VoidCallback? onStar;

  /// Le parent peut déplacer l'action dans une barre fixe au bas de l'écran.
  final bool showContinueButton;

  @override
  Widget build(BuildContext context) {
    final (title, color) = switch (correction.result) {
      AttemptResult.correct => ('✅ Bravo !', LudiColors.mastered),
      AttemptResult.partial => ('👍 Presque !', LudiColors.toReview),
      _ => ('❌ Pas tout à fait !', LudiColors.notMastered),
    };
    final openQuestion = item.type == 'OPEN_QUESTION';
    final details = openQuestion ? _keyPoints() : _details();
    // Dictée de phrases : la phrase juste, puis les mots ratés un à un.
    final showAnswer =
        correction.result != AttemptResult.correct &&
        (details.isEmpty || openQuestion || item.type == 'SENTENCE_DICTATION');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (stars case final stars?) ...[
          StarsRow(stars, onStar: onStar),
          if (item.daily != null && stars > 0)
            const Text(
              '🎲 Jeu du jour : tes étoiles comptent double !',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700),
            ),
          const SizedBox(height: 8),
        ],
        if (correction.result == AttemptResult.correct && streak >= 3) ...[
          StreakChip(streak),
          const SizedBox(height: 12),
        ],
        Cheer(
          happy: correction.result == AttemptResult.correct,
          child: Container(
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
                ] else if (showAnswer &&
                    item.type == 'SENTENCE_DICTATION' &&
                    correction.correctAnswer != null) ...[
                  const SizedBox(height: 12),
                  const Text('La phrase était :', style: TextStyle(fontSize: 19)),
                  const SizedBox(height: 4),
                  Text(
                    correction.correctAnswer!,
                    style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800, height: 1.3),
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
        ),
        if (correction.coach case final coach?) ...[
          const SizedBox(height: 12),
          LudiBubble(mood: coach.mood, message: coach.message),
        ],
        // Carte et coloriage : les bonnes zones sur le dessin (vert trouvé, orange manqué, rouge touché
        // à tort ; coloriage : les couleurs attendues).
        if (item.payload['figure'] case {'id': final String figureId}) ...[
          const SizedBox(height: 16),
          FigureLoader(
            id: figureId,
            builder: (figure) => FigureCanvas(
              figure: figure,
              plain: item.type == 'COLORING',
              colors: _figureColors(),
            ),
          ),
        ],
        if (details.isNotEmpty) ...[const SizedBox(height: 16), ...details],
        if ((correction.result != AttemptResult.correct && correction.tip != null) ||
            correction.explanation != null) ...[
          const SizedBox(height: 16),
          Card(
            color: LudiColors.primary.withValues(alpha: 0.06),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    '🧠 À retenir',
                    style: TextStyle(fontSize: 17, fontWeight: FontWeight.w800),
                  ),
                  if (correction.result != AttemptResult.correct && correction.tip != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      '💡 Astuce pour retenir : ${correction.tip}',
                      style: const TextStyle(fontSize: 18),
                    ),
                  ],
                  if (correction.explanation != null) ...[
                    const SizedBox(height: 8),
                    Text(
                      correction.explanation!,
                      style: const TextStyle(fontSize: 17, height: 1.35),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ],
        if (correction.pauseMessage case final message?) ...[
          const SizedBox(height: 20),
          Card(
            color: LudiColors.accent.withValues(alpha: 0.15),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Text('☕ $message', style: const TextStyle(fontSize: 17)),
            ),
          ),
        ],
        if (showContinueButton) ...[
          const SizedBox(height: 28),
          FilledButton(autofocus: true, onPressed: onContinue, child: const Text('Continuer')),
          if (correction.pauseMessage != null && onPause != null) ...[
            const SizedBox(height: 12),
            OutlinedButton(onPressed: onPause, child: const Text('Faire une pause')),
          ],
        ],
        if (report case final report?) ...[const SizedBox(height: 8), Center(child: report)],
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

  /// Association, défi rapide et jeux graphiques : le résultat élément par élément.
  List<Widget> _details() {
    if (correction.details.isEmpty) return const [];
    final texts = {
      for (final key in ['left', 'statements', 'items'])
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
              // Jeux en images (étape 28) : la bonne image, à côté de sa réponse.
              if (d['image'] case final String image) ...[
                ClipRRect(
                  borderRadius: BorderRadius.circular(8),
                  child: SizedBox.square(dimension: 56, child: ApiImage(image)),
                ),
                const SizedBox(width: 10),
              ],
              Expanded(child: Text(_detailText(d, texts), style: const TextStyle(fontSize: 17))),
            ],
          ),
        ),
    ];
  }

  Map<String, Color> _figureColors() => {
    for (final Json d in correction.details)
      if (d['touched'] case final String touched when d['correct'] != true)
        touched: LudiColors.notMastered,
    for (final Json d in correction.details)
      if (d['zone'] case final String zone)
        zone:
            parseColor(d['color']) ??
            (d['correct'] == true ? LudiColors.mastered : LudiColors.toReview),
  };

  String _detailText(Json d, Map<String, String> texts) {
    // Ordre et frise : la bonne place de chaque étiquette. Memory : la paire.
    if (d['position'] case final int position) return '$position. ${d['expected']}';
    if (d['pair'] case final String pair) return pair;
    final text = texts[d['id']] ?? d['text'] as String? ?? '';
    // Carte : la zone touchée à la place de la bonne.
    if (d['touched_name'] case final String touched when d['correct'] != true) {
      return '$text (tu as touché : $touched)';
    }
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

/// Ludi, le compagnon de séance (§5.76) : un mot après chaque réponse, écrit par le serveur à
/// l'âge de l'enfant.
class LudiBubble extends StatelessWidget {
  const LudiBubble({required this.mood, required this.message, super.key});

  final String mood;
  final String message;

  static String face(String mood) => switch (mood) {
    'proud' => '🥳',
    'happy' => '😊',
    'close' => '🤏',
    _ => '🤔',
  };

  @override
  Widget build(BuildContext context) => Semantics(
    label: 'Ludi : $message',
    excludeSemantics: true,
    child: Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('🧑‍🎓', style: TextStyle(fontSize: 34)),
        const SizedBox(width: 8),
        Expanded(
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: LudiColors.primary.withValues(alpha: 0.10),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Text(
              '${face(mood)} $message',
              style: const TextStyle(fontSize: 18, height: 1.3),
            ),
          ),
        ),
      ],
    ),
  );
}
