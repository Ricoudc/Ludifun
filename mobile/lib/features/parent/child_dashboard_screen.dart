import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/format.dart';
import '../../app/level_stars.dart';
import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../models/parent.dart';
import '../../models/subject.dart';
import '../rewards/progress_strip.dart';
import 'parent_providers.dart';
import 'progress_chart.dart';

const _definitions = '''
Semaine : du lundi au dimanche soir.
Séances : séances terminées dans la semaine ; la note moyenne est celle de ces séances.
Temps : temps passé à répondre (une réponse compte au plus 5 minutes), plus quelques secondes pour lire chaque correction.
Réussite par matière : maîtrise actuelle des notions déjà révisées, les notions importantes comptant davantage. Une leçon jamais révisée n'y figure pas.
À renforcer : les notions révisées pas encore maîtrisées, les plus fragiles d'abord. Une notion réussie en QCM mais jamais retrouvée sans aide y figure encore : la phrase sous la notion dit ce qui manque.
Erreurs fréquentes : ce que disent les erreurs des 30 derniers jours (confusion, oubli, réponse trop rapide…) ; 🔁 la même erreur sur la même notion dans au moins 3 séances.
Couleurs : 🟢 80 % et plus, 🟠 de 50 à 79 %, 🔴 moins de 50 %.''';

/// Écran P3 : tableau de bord d'un enfant.
class ChildDashboardScreen extends ConsumerWidget {
  const ChildDashboardScreen({required this.childId, super.key});

  final String childId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final child = ref.watch(childProvider(childId)).value;
    final board = ref.watch(dashboardProvider(childId));
    final name = child?.displayName ?? '';
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.parentHome)),
        title: Text(child == null ? '' : '${avatarOf(child)} $name · ${child.grade}'),
        actions: [
          IconButton(
            tooltip: 'Comment lire ce tableau',
            icon: const Icon(Icons.info_outline),
            onPressed: () => showModalBottomSheet<void>(
              context: context,
              builder: (_) => const SafeArea(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Text(_definitions, style: TextStyle(fontSize: 16, height: 1.5)),
                ),
              ),
            ),
          ),
          IconButton(
            tooltip: 'Historique et réglages',
            icon: const Icon(Icons.settings_outlined),
            onPressed: () => context.go(Routes.childSettings(childId)),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () {
          ref.invalidate(childProgressProvider(childId));
          return ref.refresh(dashboardProvider(childId).future);
        },
        child: CenteredBody(
          top: true,
          children: [
            if (ref.watch(childProgressProvider(childId)).value case final progress?) ...[
              ProgressStrip(progress),
              const SizedBox(height: 16),
            ],
            ...switch (board) {
              AsyncData(:final value) => _content(context, value, name),
              AsyncError(:final error) => [
                ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
                TextButton(
                  onPressed: () => ref.invalidate(dashboardProvider(childId)),
                  child: const Text('Réessayer'),
                ),
              ],
              _ => [const Center(child: CircularProgressIndicator())],
            },
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: () => context.go(Routes.childCapture(childId)),
              icon: const Icon(Icons.add_a_photo_outlined),
              label: Text('Ajouter une leçon pour $name'),
            ),
            const SizedBox(height: 12),
            if (child != null && child.devices == 0)
              OutlinedButton.icon(
                onPressed: () => context.go(Routes.childLink(childId)),
                icon: const Icon(Icons.link),
                label: const Text('Lier un appareil'),
              ),
          ],
        ),
      ),
    );
  }

  List<Widget> _content(BuildContext context, Dashboard board, String name) {
    final theme = Theme.of(context).textTheme;
    final week = board.thisWeek;
    Widget section(String title) => Padding(
      padding: const EdgeInsets.only(top: 24, bottom: 8),
      child: Text(title, style: theme.titleLarge),
    );
    return [
      Text('Cette semaine', style: theme.titleLarge),
      const SizedBox(height: 12),
      Row(
        children: [
          _Stat('📚', '${week.sessions}', week.sessions > 1 ? 'séances' : 'séance'),
          const SizedBox(width: 8),
          _Stat('⏱️', '${week.minutes}', 'min'),
          const SizedBox(width: 8),
          _Stat(
            '🎯',
            week.averageScore == null ? '–' : '${score(week.averageScore!)} / 10',
            'en moyenne',
          ),
        ],
      ),
      if (week.sessions == 0) ...[
        const SizedBox(height: 12),
        Text('$name n\'a pas encore révisé cette semaine.', style: const TextStyle(fontSize: 16)),
      ],
      if (board.reviewsDue > 0) ...[
        const SizedBox(height: 12),
        Text(
          '🔄 ${board.reviewsDue} notion${board.reviewsDue > 1 ? 's' : ''} à revoir aujourd\'hui',
          style: const TextStyle(fontSize: 16),
        ),
      ],
      section('Réussite par matière'),
      if (board.subjects.isEmpty)
        const Text('Les matières apparaîtront après les premières révisions.')
      else
        for (final s in board.subjects)
          _Row(
            leading: _Dot(s.color),
            label: '${Subjects.emoji(s.subject)} ${Subjects.label(s.subject)}',
            value: '${s.mastery} %',
          ),
      if (board.toStrengthen.isNotEmpty) ...[
        section('À renforcer'),
        for (final n in board.toStrengthen)
          _Row(
            leading: _Dot(n.status == 'not_mastered' ? 'red' : 'orange'),
            label: n.label,
            detail: [?n.explanation, ?n.lessonTitle].join(' · '),
            trailing: LevelStars(n.level, size: 14),
          ),
      ],
      if (board.recurringErrors.isNotEmpty || board.errorTypes.isNotEmpty) ...[
        section('Erreurs fréquentes'),
        for (final e in board.recurringErrors)
          _Row(
            leading: const Text('🔁', style: TextStyle(fontSize: 16)),
            label: '${e.label} : ${e.errorLabel.toLowerCase()}',
            detail: [?e.lessonTitle, 'dans ${e.sessions} séances'].join(' · '),
          ),
        if (board.errorTypes.isNotEmpty) ...[
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final e in board.errorTypes) Chip(label: Text('${e.label} · ${e.count}')),
            ],
          ),
        ],
      ],
      const SizedBox(height: 8),
      OutlinedButton.icon(
        onPressed: () => context.go(Routes.childGoals(childId)),
        icon: const Icon(Icons.flag_outlined),
        label: const Text('Objectifs et contrôles'),
      ),
      const SizedBox(height: 8),
      OutlinedButton.icon(
        onPressed: () => context.go(Routes.childSkills(childId)),
        icon: const Icon(Icons.star_outline_rounded),
        label: const Text('Compétences par leçon'),
      ),
      section('Progression'),
      Text(switch (board.trend) {
        'up' => 'Note moyenne par semaine · en progression ↗',
        'down' => 'Note moyenne par semaine · en baisse ↘',
        'stable' => 'Note moyenne par semaine · stable →',
        _ => 'Note moyenne par semaine',
      }, style: const TextStyle(fontSize: 15, color: Colors.black54)),
      const SizedBox(height: 12),
      ProgressChart(weeks: board.weeks),
      if (board.activities.isNotEmpty) ...[
        section('Activités de la semaine'),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            for (final MapEntry(:key, :value) in board.activities.entries)
              Chip(
                label: Text(
                  '${activityLabels[key]?.$1 ?? '🎲'} ${activityLabels[key]?.$2 ?? key} $value',
                ),
              ),
          ],
        ),
      ],
    ];
  }
}

class _Stat extends StatelessWidget {
  const _Stat(this.emoji, this.value, this.label);

  final String emoji;
  final String value;
  final String label;

  @override
  Widget build(BuildContext context) => Expanded(
    child: Card(
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 8),
        child: Column(
          children: [
            Text(emoji, style: const TextStyle(fontSize: 22)),
            const SizedBox(height: 4),
            FittedBox(
              child: Text(value, style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w800)),
            ),
            Text(label, style: const TextStyle(color: Colors.black54)),
          ],
        ),
      ),
    ),
  );
}

/// Pastille de couleur : toujours accompagnée du pourcentage écrit.
class _Dot extends StatelessWidget {
  const _Dot(this.color);

  final String color;

  @override
  Widget build(BuildContext context) => Container(
    width: 14,
    height: 14,
    decoration: BoxDecoration(
      shape: BoxShape.circle,
      color: switch (color) {
        'green' => LudiColors.mastered,
        'orange' => LudiColors.toReview,
        _ => LudiColors.notMastered,
      },
    ),
  );
}

class _Row extends StatelessWidget {
  const _Row({required this.leading, required this.label, this.value, this.trailing, this.detail});

  final Widget leading;
  final String label;
  final String? value;
  final Widget? trailing;
  final String? detail;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 6),
    child: Row(
      children: [
        leading,
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(label, style: const TextStyle(fontSize: 17)),
              if (detail != null)
                Text(detail!, style: const TextStyle(fontSize: 13, color: Colors.black54)),
            ],
          ),
        ),
        ?trailing,
        if (value != null)
          Text(value!, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w700)),
      ],
    ),
  );
}
