import 'package:flutter/material.dart';

import '../api/models.dart';
import '../main.dart';
import 'quiz_screen.dart';

/// Écrans 2 et 3 : « J'ai compris ta leçon » puis « Comment veux-tu réviser ? ».
class LessonScreen extends StatelessWidget {
  final Lesson lesson;
  const LessonScreen({super.key, required this.lesson});

  static const modes = [
    ('quiz_rapide', '⚡', 'Quiz rapide', 'QCM et vrai/faux'),
    ('entrainement', '🧠', 'Je m\'entraîne', 'Tous les types d\'exercices'),
    ('flashcards', '🃏', 'Cartes mémoire', 'Retourne les cartes'),
    ('defi', '🏆', 'Défi', '60 secondes chrono'),
    ('revision', '🎯', 'Mes points faibles', 'Seulement ce qui n\'est pas encore acquis'),
  ];

  Future<void> _start(BuildContext context, String mode) async {
    try {
      final session = await api.startSession(lesson.id, mode);
      if (!context.mounted) return;
      await Navigator.of(context).push(MaterialPageRoute(builder: (_) => QuizScreen(session: session)));
    } catch (e) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('$e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(lesson.title)),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('✅ J\'ai compris ta leçon !', style: theme.textTheme.headlineSmall),
          const SizedBox(height: 12),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text('Matière : ${lesson.subject}'),
                Text('Niveau : ${lesson.grade}'),
                Text('Sujet : ${lesson.title}'),
                const SizedBox(height: 8),
                Text(lesson.summary, style: theme.textTheme.bodyMedium),
              ]),
            ),
          ),
          const SizedBox(height: 12),
          ExpansionTile(
            title: Text('À retenir (${lesson.notions.length} notions)'),
            children: [
              for (final n in lesson.notions)
                ListTile(
                  leading: Text(n.importance == 'essentielle' ? '⭐' : '•', style: const TextStyle(fontSize: 20)),
                  title: Text(n.label),
                  subtitle: Text(n.content),
                ),
            ],
          ),
          const SizedBox(height: 16),
          Text('🎮 Comment veux-tu réviser ?', style: theme.textTheme.titleLarge),
          const SizedBox(height: 8),
          for (final (mode, emoji, title, subtitle) in modes)
            Card(
              child: ListTile(
                leading: Text(emoji, style: const TextStyle(fontSize: 28)),
                title: Text(title),
                subtitle: Text(subtitle),
                onTap: () => _start(context, mode),
              ),
            ),
        ],
      ),
    );
  }
}
