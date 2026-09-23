import 'package:flutter/material.dart';

import '../api/models.dart';
import '../main.dart';
import 'lesson_screen.dart';

/// Suivi de la progression — l'enfant est comparé à lui-même, jamais aux autres.
class ProgressScreen extends StatelessWidget {
  final Child child;
  const ProgressScreen({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Progression de ${child.displayName}')),
      body: FutureBuilder<ChildProgress>(
        future: api.progress(child.id),
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) return Center(child: Text('${snap.error}'));
          final p = snap.data!;
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Card(
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text('⏱️ ${p.minutesLast7Days.round()} min de révision cette semaine'),
                    Text('📚 ${p.lessons} leçon(s)'),
                    Text('🎯 ${(p.successRate * 100).round()} % de réussite'),
                  ]),
                ),
              ),
              const SizedBox(height: 16),
              for (final s in p.subjects)
                ListTile(
                  leading: Text(s.successRate >= 0.8 ? '🟢' : s.successRate >= 0.5 ? '🟠' : '🔴'),
                  title: Text(s.subject),
                  trailing: Text('${(s.successRate * 100).round()} %'),
                ),
              if (p.dueReviews.isNotEmpty) ...[
                const Divider(),
                const Text('🔄 À réviser aujourd\'hui', style: TextStyle(fontWeight: FontWeight.bold)),
                for (final n in p.dueReviews) _NotionTile(notion: n),
              ],
              if (p.toStrengthen.isNotEmpty) ...[
                const Divider(),
                const Text('💪 À renforcer', style: TextStyle(fontWeight: FontWeight.bold)),
                for (final n in p.toStrengthen) _NotionTile(notion: n),
              ],
            ],
          );
        },
      ),
    );
  }
}

class _NotionTile extends StatelessWidget {
  final NotionProgress notion;
  const _NotionTile({required this.notion});

  @override
  Widget build(BuildContext context) {
    return ListTile(
      title: Text(notion.label),
      subtitle: Text(notion.levelLabel),
      trailing: const Icon(Icons.play_circle_outline),
      onTap: () async {
        final lesson = await api.getLesson(notion.lessonId);
        if (!context.mounted) return;
        Navigator.of(context).push(MaterialPageRoute(builder: (_) => LessonScreen(lesson: lesson)));
      },
    );
  }
}
