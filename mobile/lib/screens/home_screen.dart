import 'package:flutter/material.dart';

import '../api/models.dart';
import '../main.dart';
import 'capture_screen.dart';
import 'lesson_screen.dart';
import 'progress_screen.dart';

/// Écran 1 : accueil, « Nouvelle révision » et leçons déjà photographiées.
class HomeScreen extends StatefulWidget {
  final Child child;
  const HomeScreen({super.key, required this.child});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late Future<List<LessonSummary>> _lessons;

  @override
  void initState() {
    super.initState();
    _refresh();
  }

  void _refresh() => setState(() => _lessons = api.listLessons(widget.child.id));

  Future<void> _open(Widget screen) async {
    await Navigator.of(context).push(MaterialPageRoute(builder: (_) => screen));
    _refresh();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Salut ${widget.child.displayName} !'),
        actions: [
          IconButton(
            tooltip: 'Ma progression',
            icon: const Icon(Icons.insights),
            onPressed: () => _open(ProgressScreen(child: widget.child)),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _open(CaptureScreen(child: widget.child)),
        icon: const Icon(Icons.photo_camera),
        label: const Text('Nouvelle révision'),
      ),
      body: FutureBuilder<List<LessonSummary>>(
        future: _lessons,
        builder: (context, snap) {
          if (snap.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snap.hasError) return Center(child: Text('${snap.error}'));
          final lessons = snap.data!;
          if (lessons.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(32),
                child: Text('📸 Photographie ta première leçon pour commencer !', textAlign: TextAlign.center),
              ),
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
            itemCount: lessons.length,
            separatorBuilder: (_, __) => const SizedBox(height: 8),
            itemBuilder: (_, i) => Card(
              child: ListTile(
                leading: const Icon(Icons.menu_book),
                title: Text(lessons[i].title),
                subtitle: Text(lessons[i].subject),
                trailing: const Icon(Icons.chevron_right),
                onTap: () async => _open(LessonScreen(lesson: await api.getLesson(lessons[i].id))),
              ),
            ),
          );
        },
      ),
    );
  }
}
