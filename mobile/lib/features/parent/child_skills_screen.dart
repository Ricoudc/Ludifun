import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/level_stars.dart';
import '../../app/router.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../models/level.dart';
import '../../models/parent.dart';
import '../../models/subject.dart';
import 'parent_providers.dart';

const _levels = '''
Chaque notion a un niveau de 0 à 5 :
0 jamais travaillée · 1 découverte · 2 fragile · 3 en cours d'acquisition · 4 maîtrisée · 5 très bien maîtrisée (retenue dans le temps).

« Maîtrisée » ne veut pas dire « réussit les QCM » : il faut aussi retrouver la réponse sans la voir, et appliquer une règle quand la leçon le permet. Sous chaque notion, une phrase dit ce qui manque encore.

Une compétence est ce que la leçon demande de savoir faire ; son niveau suit celui de ses notions, la plus fragile comptant beaucoup.''';

/// Compétences et notions de chaque leçon, avec leur niveau et ce qui manque encore.
class ChildSkillsScreen extends ConsumerWidget {
  const ChildSkillsScreen({required this.childId, super.key});

  final String childId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lessons = ref.watch(childSkillsProvider(childId));
    final name = ref.watch(childProvider(childId)).value?.displayName;
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.childDashboard(childId))),
        title: Text(name == null ? 'Compétences' : 'Compétences · $name'),
        actions: [
          IconButton(
            tooltip: 'Comment lire les niveaux',
            icon: const Icon(Icons.info_outline),
            onPressed: () => showModalBottomSheet<void>(
              context: context,
              builder: (_) => const SafeArea(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Text(_levels, style: TextStyle(fontSize: 16, height: 1.5)),
                ),
              ),
            ),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(childSkillsProvider(childId).future),
        child: CenteredBody(
          top: true,
          children: switch (lessons) {
            AsyncData(value: []) => [
              const Text(
                'Les compétences apparaîtront quand une leçon aura été analysée.',
                style: TextStyle(fontSize: 17),
              ),
            ],
            AsyncData(:final value) => [for (final lesson in value) _LessonCard(lesson)],
            AsyncError(:final error) => [
              ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
              TextButton(
                onPressed: () => ref.invalidate(childSkillsProvider(childId)),
                child: const Text('Réessayer'),
              ),
            ],
            _ => [const Center(child: CircularProgressIndicator())],
          },
        ),
      ),
    );
  }
}

class _LessonCard extends StatelessWidget {
  const _LessonCard(this.lesson);

  final LessonProgress lesson;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context).textTheme;
    final others = lesson.notionsWithoutSkill;
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${Subjects.emoji(lesson.subject)} ${lesson.title ?? 'Leçon'}',
              style: theme.titleLarge,
            ),
            const SizedBox(height: 8),
            for (final skill in lesson.skills)
              _Group(
                title: skill.label,
                subtitle: verbLabels[skill.verb],
                level: skill.level,
                notions: lesson.notionsOf(skill),
              ),
            if (others.isNotEmpty)
              _Group(title: lesson.skills.isEmpty ? 'Notions' : 'Autres notions', notions: others),
          ],
        ),
      ),
    );
  }
}

/// Une compétence (titre, niveau) et ses notions, dépliables.
class _Group extends StatelessWidget {
  const _Group({required this.title, required this.notions, this.subtitle, this.level});

  final String title;
  final String? subtitle;
  final int? level;
  final List<NotionProgress> notions;

  @override
  Widget build(BuildContext context) => ExpansionTile(
    tilePadding: EdgeInsets.zero,
    childrenPadding: const EdgeInsets.only(left: 8, bottom: 8),
    shape: const Border(),
    title: Text(title, style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600)),
    subtitle: level == null
        ? null
        : Row(
            children: [
              LevelStars(level!, size: 16),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  '${Levels.label(level!)}${subtitle == null ? '' : ' · $subtitle'}',
                  style: const TextStyle(color: Colors.black54),
                ),
              ),
            ],
          ),
    children: [
      for (final notion in notions)
        ListTile(
          contentPadding: EdgeInsets.zero,
          dense: true,
          title: Text(notion.label, style: const TextStyle(fontSize: 16)),
          subtitle: NotionFacts(notion),
          trailing: LevelStars(notion.level, size: 14),
        ),
    ],
  );
}

/// Ce qui a été observé (chiffres), séparé de l'interprétation du moteur (CDC §131).
class NotionFacts extends StatelessWidget {
  const NotionFacts(this.notion, {super.key});

  final NotionProgress notion;

  @override
  Widget build(BuildContext context) {
    final rates = [
      for (final r in notion.levelRates)
        if (r.rate != null) '${r.name} ${(r.rate! * 100).round()} %',
    ];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (notion.facts case final facts?) Text('📊 $facts'),
        if (rates.isNotEmpty)
          Text(
            'Réussite par niveau : ${rates.join(' · ')}'
            '${notion.independence == null ? '' : ' · seul ${(notion.independence! * 100).round()} %'}',
            style: const TextStyle(fontSize: 12, color: Colors.black54),
          ),
        Text('💬 ${notion.explanation}', style: const TextStyle(fontStyle: FontStyle.italic)),
      ],
    );
  }
}
