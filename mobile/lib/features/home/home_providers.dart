import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/session.dart';
import '../../models/account.dart';
import '../../models/lesson.dart';

/// Profil de l'enfant ; appelé à l'ouverture, il détecte aussi un appareil délié.
final meProvider = FutureProvider.autoDispose<Child>((ref) => ref.watch(apiProvider).me());

final missionProvider = FutureProvider.autoDispose<Mission>(
  (ref) => ref.watch(apiProvider).mission(),
);

/// Horloge de l'affichage (« à revoir jeudi »), remplaçable dans les tests.
final nowProvider = Provider<DateTime Function()>((ref) => DateTime.now);

const lessonsRefresh = Duration(seconds: 3);

/// Dernières leçons ; tant qu'une analyse est en cours, la liste se met à jour seule.
final lessonsProvider = FutureProvider.autoDispose<List<LessonSummary>>((ref) async {
  final lessons = await ref.watch(apiProvider).lessons();
  if (lessons.any((l) => l.status.inProgress)) {
    final timer = Timer(lessonsRefresh, () {
      ref.invalidateSelf();
      ref.invalidate(missionProvider);
    });
    ref.onDispose(timer.cancel);
  }
  return lessons;
});

void refreshHome(WidgetRef ref) {
  ref.invalidate(lessonsProvider);
  ref.invalidate(missionProvider);
}
