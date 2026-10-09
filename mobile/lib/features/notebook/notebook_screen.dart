import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../app/format.dart';
import '../../app/router.dart';
import '../../app/theme.dart';
import '../../app/widgets.dart';
import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/homework.dart';
import '../../models/lesson.dart';
import '../../models/subject.dart';
import '../home/home_providers.dart';

/// « Mon cahier » : relire ses leçons (fiche de révision, vidéos et exercices proposés) et ses
/// devoirs, sans faire de jeux.
class NotebookScreen extends ConsumerWidget {
  const NotebookScreen({this.homework = false, super.key});

  /// Ouvrir directement l'onglet des devoirs (retour d'un devoir relu).
  final bool homework;

  @override
  Widget build(BuildContext context, WidgetRef ref) => DefaultTabController(
    length: 2,
    initialIndex: homework ? 1 : 0,
    child: Scaffold(
      appBar: AppBar(
        leading: BackButton(onPressed: () => context.go(Routes.childHome)),
        title: const Text('📚 Mon cahier'),
        bottom: const TabBar(
          tabs: [
            Tab(text: 'Mes leçons'),
            Tab(text: 'Mes devoirs'),
          ],
        ),
      ),
      body: const TabBarView(children: [_Lessons(), _Homework()]),
    ),
  );
}

class _Lessons extends ConsumerWidget {
  const _Lessons();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lessons = ref.watch(lessonsProvider);
    return switch (lessons) {
      AsyncData(:final value) => _bySubject(context, [
        for (final l in value)
          if (l.status == LessonStatus.ready) l,
      ]),
      AsyncError(:final error) => CenteredBody(
        children: [
          ErrorMessage(error is ApiException ? error.message : ApiException.unexpected),
          TextButton(onPressed: () => refreshHome(ref), child: const Text('Réessayer')),
        ],
      ),
      _ => const Center(child: CircularProgressIndicator()),
    };
  }

  Widget _bySubject(BuildContext context, List<LessonSummary> lessons) {
    if (lessons.isEmpty) {
      return const CenteredBody(
        children: [
          Text(
            'Ton cahier est vide pour l\'instant : prends une leçon en photo, elle apparaîtra ici.',
            style: TextStyle(fontSize: 17),
          ),
        ],
      );
    }
    final subjects = <String?, List<LessonSummary>>{};
    for (final lesson in lessons) {
      subjects.putIfAbsent(lesson.subject, () => []).add(lesson);
    }
    return CenteredBody(
      top: true,
      children: [
        const Text(
          'Relis tes leçons quand tu veux : ce qu\'il faut retenir, les explications, '
          'les vidéos et les exercices proposés.',
          style: TextStyle(fontSize: 16, color: Colors.black54),
        ),
        for (final MapEntry(key: subject, value: list) in subjects.entries) ...[
          const SizedBox(height: 16),
          Text(
            '${Subjects.emoji(subject)} ${Subjects.label(subject)}',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          for (final lesson in list)
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.menu_book_outlined, color: LudiColors.primary),
              title: Text(lesson.title ?? 'Ma leçon', style: const TextStyle(fontSize: 18)),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => context.go(Routes.lessonSheet(lesson.id)),
            ),
        ],
      ],
    );
  }
}

class _Homework extends ConsumerStatefulWidget {
  const _Homework();

  @override
  ConsumerState<_Homework> createState() => _HomeworkState();
}

class _HomeworkState extends ConsumerState<_Homework> {
  final _items = <HomeworkSummary>[];
  String? _nextBefore;
  bool _loading = true;
  bool _complete = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadMore();
  }

  Future<void> _loadMore() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final page = await ref
          .read(apiProvider)
          .myHomework(before: _items.isEmpty ? null : _nextBefore);
      _items.addAll(page.homework);
      _nextBefore = page.nextBefore;
      _complete = page.nextBefore == null;
    } on ApiException catch (error) {
      _error = error.message;
    }
    if (mounted) setState(() => _loading = false);
  }

  @override
  Widget build(BuildContext context) {
    final now = ref.watch(nowProvider)();
    final shown = [
      for (final h in _items)
        if (h.status != HomeworkStatus.failed && h.status != HomeworkStatus.preparing) h,
    ];
    return CenteredBody(
      top: true,
      children: [
        if (shown.isEmpty && !_loading && _error == null)
          const Text(
            'Pas encore de devoirs : avec « Aide aux devoirs », tes exercices apparaîtront ici.',
            style: TextStyle(fontSize: 17),
          ),
        for (final item in shown)
          Card(
            margin: const EdgeInsets.only(bottom: 10),
            child: ListTile(
              title: Text(
                item.statement ?? 'Mon exercice',
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 17),
              ),
              subtitle: Text(
                '${whenAt(item.createdAt, now)} · ${switch (item.status) {
                  HomeworkStatus.solved => '✅ réussi',
                  HomeworkStatus.guided => '🧭 correction guidée',
                  _ => '⏸️ pas terminé',
                }}',
              ),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => context.go(Routes.homework(item.id, fromNotebook: true)),
            ),
          ),
        if (_error != null) ErrorMessage(_error!),
        if (_loading)
          const Padding(
            padding: EdgeInsets.all(12),
            child: Center(child: CircularProgressIndicator()),
          )
        else if (!_complete || _error != null)
          TextButton(onPressed: _loadMore, child: const Text('Voir les devoirs plus anciens')),
      ],
    );
  }
}
