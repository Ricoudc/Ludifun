import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/level_stars.dart';
import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../models/level.dart';
import '../../models/programme.dart';
import '../../models/subject.dart';
import 'parent_providers.dart';

const _about = '''
Le programme de l'Éducation nationale pour la classe de l'enfant, résumé par Ludifun : matière, domaine, compétence, puis ce qu'on y apprend.

Chaque notion d'une leçon y est rangée automatiquement, d'après ses mots (sans IA) :
✅ maîtrisé : toutes ses notions sont au niveau 4 ou plus ;
🟠 commencé : une leçon en parle, à travailler encore ;
⚪ pas encore vu : aucune leçon pour l'instant.

C'est un repère, pas un bulletin : l'ordre des leçons dépend de la classe, et le résumé peut être imparfait.''';

/// Le programme de la classe (§105) : ce qui est maîtrisé, commencé, ou pas encore vu.
class ChildProgrammeScreen extends ConsumerWidget {
  const ChildProgrammeScreen({required this.childId, super.key});

  final String childId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final programme = ref.watch(programmeProvider(childId));
    final name = ref.watch(childProvider(childId)).value?.displayName;
    final grade = programme.value?.grade;
    return Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.childDashboard(childId))),
        title: Text(
          grade == null ? 'Programme' : 'Programme de $grade${name == null ? '' : ' · $name'}',
        ),
        actions: [
          IconButton(
            tooltip: 'Comment lire le programme',
            icon: const Icon(Icons.info_outline),
            onPressed: () => showModalBottomSheet<void>(
              context: context,
              builder: (_) => const SafeArea(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Text(_about, style: TextStyle(fontSize: 16, height: 1.5)),
                ),
              ),
            ),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () => ref.refresh(programmeProvider(childId).future),
        child: CenteredBody(
          top: true,
          children: switch (programme) {
            AsyncData(:final value) => [
              for (final subject in value.subjects) _SubjectCard(subject),
              Text(
                '${value.source} (version ${value.version})',
                style: const TextStyle(fontSize: 12, color: Colors.black54),
              ),
            ],
            AsyncError(:final error) => [
              ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
              TextButton(
                onPressed: () => ref.invalidate(programmeProvider(childId)),
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

class _SubjectCard extends StatelessWidget {
  const _SubjectCard(this.subject);

  final ProgrammeSubject subject;

  @override
  Widget build(BuildContext context) {
    final seen = subject.started + subject.mastered;
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      clipBehavior: Clip.antiAlias,
      child: ExpansionTile(
        leading: Text(Subjects.emoji(subject.subject), style: const TextStyle(fontSize: 24)),
        title: Text(
          Subjects.label(subject.subject),
          style: Theme.of(context).textTheme.titleMedium,
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('$seen / ${subject.total} vus · ${subject.mastered} maîtrisés'),
            const SizedBox(height: 6),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: subject.total == 0 ? 0 : seen / subject.total,
                minHeight: 6,
                color: subject.mastered == seen && seen > 0
                    ? LudiColors.mastered
                    : LudiColors.primary,
              ),
            ),
          ],
        ),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        expandedCrossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final domain in subject.domains) ...[
            Padding(
              padding: const EdgeInsets.only(top: 12, bottom: 4),
              child: Text(domain.title, style: Theme.of(context).textTheme.titleSmall),
            ),
            for (final competence in domain.competences)
              for (final sub in competence.subs) _SubRow(sub),
          ],
          if (subject.elsewhere.isNotEmpty) ...[
            Padding(
              padding: const EdgeInsets.only(top: 12, bottom: 4),
              child: Text(
                'Dans le programme d\'une autre classe',
                style: Theme.of(context).textTheme.titleSmall,
              ),
            ),
            for (final sub in subject.elsewhere) _SubRow(sub, showGrades: true),
          ],
          if (subject.unplaced.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(
                'Hors du résumé du programme : ${subject.unplaced.map((n) => n.label).join(', ')}',
                style: const TextStyle(fontSize: 13, color: Colors.black54),
              ),
            ),
        ],
      ),
    );
  }
}

class _SubRow extends StatelessWidget {
  const _SubRow(this.sub, {this.showGrades = false});

  final SubCompetence sub;
  final bool showGrades;

  @override
  Widget build(BuildContext context) {
    final mark = switch (sub.status) {
      SubStatus.mastered => '✅',
      SubStatus.started => '🟠',
      SubStatus.notSeen => '⚪',
    };
    final grades = sub.grades.length == 1
        ? sub.grades.single
        : '${sub.grades.first} à ${sub.grades.last}';
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(mark, style: const TextStyle(fontSize: 16)),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  showGrades ? '${sub.title} (programme de $grades)' : sub.title,
                  style: TextStyle(
                    fontSize: 15,
                    color: sub.status == SubStatus.notSeen ? Colors.black54 : null,
                  ),
                ),
                for (final notion in sub.notions)
                  Text(
                    '${notion.label} · ${Levels.label(notion.level)}',
                    style: TextStyle(fontSize: 13, color: levelColor(notion.level)),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
