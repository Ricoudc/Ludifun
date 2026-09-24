import 'package:flutter/material.dart';

import '../../app/format.dart';
import '../../app/level_stars.dart';
import '../../app/theme.dart';
import '../../models/level.dart';
import '../../models/session.dart';

/// Écran 7 : bilan de la séance.
class ReportView extends StatelessWidget {
  const ReportView({
    required this.report,
    required this.onReviewErrors,
    required this.onDone,
    super.key,
  });

  final Report report;
  final VoidCallback? onReviewErrors;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context).textTheme;
    final mastered = report.withStatus(KnowledgeStatus.mastered);
    final toReview = report.withStatus(KnowledgeStatus.toReview);
    final notMastered = report.withStatus(KnowledgeStatus.notMastered);
    String notions(int n) => n > 1 ? 'notions' : 'notion';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          report.lessonMastered ? '🏆 Leçon maîtrisée !' : '🎉 Révision terminée !',
          textAlign: TextAlign.center,
          style: theme.headlineMedium,
        ),
        const SizedBox(height: 20),
        Text(
          '${score(report.scoreOn10)} / 10',
          textAlign: TextAlign.center,
          style: theme.displayMedium?.copyWith(
            fontWeight: FontWeight.w900,
            color: LudiColors.primary,
          ),
        ),
        const SizedBox(height: 8),
        LinearProgressIndicator(
          value: report.scoreOn10 / 10,
          minHeight: 14,
          borderRadius: BorderRadius.circular(7),
        ),
        const SizedBox(height: 24),
        if (mastered.isNotEmpty)
          _Count(
            '✅ ${mastered.length} ${notions(mastered.length)} ${mastered.length > 1 ? 'maîtrisées' : 'maîtrisée'}',
          ),
        if (toReview.isNotEmpty)
          _Count('🟠 ${toReview.length} ${notions(toReview.length)} à revoir'),
        if (notMastered.isNotEmpty)
          _Count(
            '🔴 ${notMastered.length} ${notions(notMastered.length)} '
            '${notMastered.length > 1 ? 'pas encore maîtrisées' : 'pas encore maîtrisée'}',
          ),
        const SizedBox(height: 16),
        if (mastered.isNotEmpty)
          _Labels('Maîtrisé', [for (final k in mastered) '✓ ${k.label}'], LudiColors.mastered),
        if (toReview.isNotEmpty || notMastered.isNotEmpty)
          _Labels('À revoir', [
            for (final k in [...notMastered, ...toReview]) '⚠ ${k.label}',
          ], LudiColors.toReview),
        if (report.levelledUp.isNotEmpty) ...[
          const SizedBox(height: 4),
          Text('⬆️ Tu as progressé :', style: theme.titleMedium),
          const SizedBox(height: 6),
          for (final k in report.levelledUp)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      '${k.label} · ${Levels.label(k.level).toLowerCase()}',
                      style: const TextStyle(fontSize: 17),
                    ),
                  ),
                  LevelStars(k.level),
                ],
              ),
            ),
        ],
        if (report.nextReviewAt != null) ...[
          const SizedBox(height: 16),
          Text(
            '📅 Prochaine révision : ${longDate(report.nextReviewAt!)}',
            style: const TextStyle(fontSize: 18),
          ),
        ],
        const SizedBox(height: 28),
        if (report.canReviewErrors && onReviewErrors != null) ...[
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: LudiColors.accent),
            onPressed: onReviewErrors,
            child: const Text('Revoir mes erreurs'),
          ),
          const SizedBox(height: 12),
        ],
        OutlinedButton(onPressed: onDone, child: const Text('Terminer')),
      ],
    );
  }
}

class _Count extends StatelessWidget {
  const _Count(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Text(text, style: const TextStyle(fontSize: 19, fontWeight: FontWeight.w600)),
  );
}

class _Labels extends StatelessWidget {
  const _Labels(this.title, this.labels, this.color);

  final String title;
  final List<String> labels;
  final Color color;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('$title :', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 6),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final label in labels)
              Chip(
                label: Text(label),
                backgroundColor: color.withValues(alpha: 0.12),
                side: BorderSide(color: color),
              ),
          ],
        ),
      ],
    ),
  );
}
