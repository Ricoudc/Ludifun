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
import 'lessons_panel.dart';
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
          ref
            ..invalidate(childProgressProvider(childId))
            ..invalidate(allLessonsProvider(childId));
          return ref.refresh(dashboardProvider(childId).future);
        },
        child: CenteredBody(
          top: true,
          children: [
            if (ref.watch(childProgressProvider(childId)).value case final progress?) ...[
              ProgressStrip(progress),
              const SizedBox(height: 16),
            ],
            // Ce que le parent fait le plus souvent, en haut plutôt qu'au bout de la page.
            FilledButton.icon(
              onPressed: () => context.go(Routes.childCapture(childId)),
              icon: const Icon(Icons.add_a_photo_outlined),
              label: Text('Ajouter une leçon pour $name'),
            ),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () => context.go(Routes.childAssistant(childId)),
              icon: const Icon(Icons.tips_and_updates_outlined),
              label: Text('Sur quoi faire travailler $name ?'),
            ),
            const SizedBox(height: 12),
            _Shortcuts([
              _Shortcut(
                Icons.fact_check_outlined,
                'Voir ses erreurs aux questions',
                () => context.go(Routes.childMistakes(childId)),
              ),
              _Shortcut(Icons.help_outline, switch (board.value?.helpThisWeek ?? 0) {
                0 => 'Aides demandées',
                final n => 'Aides demandées ($n cette semaine)',
              }, () => context.go(Routes.childHelp(childId))),
              _Shortcut(Icons.outlined_flag, switch (board.value?.reportsToSee ?? 0) {
                0 => 'Questions signalées',
                final n => 'Questions signalées ($n à voir)',
              }, () => context.go(Routes.childReports(childId))),
              _Shortcut(
                Icons.flag_outlined,
                'Objectifs et contrôles',
                () => context.go(Routes.childGoals(childId)),
              ),
              _Shortcut(
                Icons.star_outline_rounded,
                'Compétences par leçon',
                () => context.go(Routes.childSkills(childId)),
              ),
              _Shortcut(
                Icons.edit_note,
                'Aide aux devoirs',
                () => context.go(Routes.childHomework(childId)),
              ),
              _Shortcut(
                Icons.record_voice_over_outlined,
                'Enseigne-moi',
                () => context.go(Routes.childTeach(childId)),
              ),
              _Shortcut(
                Icons.school_outlined,
                child == null ? 'Programme de la classe' : 'Programme de ${child.grade}',
                () => context.go(Routes.childProgramme(childId)),
              ),
              if (child != null && child.devices == 0)
                _Shortcut(
                  Icons.link,
                  'Lier un appareil',
                  () => context.go(Routes.childLink(childId)),
                ),
            ]),
            const SizedBox(height: 16),
            LessonsPanel(childId: childId),
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
      if (board.summary.isNotEmpty) ...[
        Card(
          color: LudiColors.primary.withValues(alpha: 0.06),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('En bref · 7 derniers jours', style: theme.titleMedium),
                const SizedBox(height: 8),
                for (final line in board.summary)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Text(
                      line,
                      style: TextStyle(
                        fontSize: 16,
                        height: 1.3,
                        fontWeight: line.startsWith('👉') ? FontWeight.w600 : null,
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 20),
      ],
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

/// Raccourcis du tableau de bord, deux par ligne.
class _Shortcuts extends StatelessWidget {
  const _Shortcuts(this.items);

  final List<_Shortcut> items;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      for (var i = 0; i < items.length; i += 2)
        Padding(
          padding: const EdgeInsets.only(bottom: 8),
          child: IntrinsicHeight(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(child: items[i]),
                const SizedBox(width: 8),
                Expanded(child: i + 1 < items.length ? items[i + 1] : const SizedBox()),
              ],
            ),
          ),
        ),
    ],
  );
}

class _Shortcut extends StatelessWidget {
  const _Shortcut(this.icon, this.label, this.onTap);

  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => Card(
    clipBehavior: Clip.antiAlias,
    child: InkWell(
      onTap: onTap,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: LudiColors.primary),
            const SizedBox(height: 6),
            Text(label, style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600)),
          ],
        ),
      ),
    ),
  );
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
