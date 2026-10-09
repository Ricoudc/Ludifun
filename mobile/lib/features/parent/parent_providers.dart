import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/session.dart';
import '../../models/account.dart';
import '../../models/lesson.dart';
import '../../models/parent.dart';
import '../../models/programme.dart';
import '../../models/rewards.dart';

final childrenProvider = FutureProvider.autoDispose<List<Child>>(
  (ref) => ref.watch(apiProvider).children(),
);

/// Le compte du parent : l'adresse est-elle confirmée ? (bandeau de l'accueil parent)
final parentProfileProvider = FutureProvider.autoDispose<ParentProfile>(
  (ref) => ref.watch(apiProvider).parent(),
);

/// Un enfant de la famille (dans la liste déjà chargée).
final childProvider = FutureProvider.autoDispose.family<Child?, String>((ref, id) async {
  final children = await ref.watch(childrenProvider.future);
  return children.where((c) => c.id == id).firstOrNull;
});

final dashboardProvider = FutureProvider.autoDispose.family<Dashboard, String>(
  (ref, childId) => ref.watch(apiProvider).dashboard(childId),
);

/// XP, série et badges de l'enfant (étape 20).
final childProgressProvider = FutureProvider.autoDispose.family<Progress, String>(
  (ref, childId) => ref.watch(apiProvider).progress(childId: childId),
);

final childSkillsProvider = FutureProvider.autoDispose.family<List<LessonProgress>, String>(
  (ref, childId) => ref.watch(apiProvider).childSkills(childId),
);

final programmeProvider = FutureProvider.autoDispose.family<Programme, String>(
  (ref, childId) => ref.watch(apiProvider).programme(childId),
);

final examsProvider = FutureProvider.autoDispose.family<List<Exam>, String>(
  (ref, childId) => ref.watch(apiProvider).exams(childId),
);

/// Leçons prêtes d'un enfant, vues par le parent (pour composer un contrôle).
final childLessonsProvider = FutureProvider.autoDispose.family<List<LessonSummary>, String>(
  (ref, childId) async => [
    for (final lesson in await ref.watch(apiProvider).lessons(childId: childId))
      if (lesson.status == LessonStatus.ready) lesson,
  ],
);

final devicesProvider = FutureProvider.autoDispose.family<List<Device>, String>(
  (ref, childId) => ref.watch(apiProvider).devices(childId),
);

/// Libellés des activités pour le parent.
const activityLabels = {
  'MCQ': ('🎮', 'Quiz'),
  'TRUE_FALSE': ('✅', 'Vrai ou faux'),
  'FILL_BLANK': ('✍️', 'Textes à trous'),
  'MATCH': ('🔗', 'Associations'),
  'SPEED_CHALLENGE': ('⚡', 'Défis rapides'),
  'FLASHCARD': ('🃏', 'Cartes'),
  'OPEN_QUESTION': ('💬', 'Questions à rédiger'),
  'ORDER': ('🔢', 'Remettre dans l\'ordre'),
  'TIMELINE': ('📅', 'Frises'),
  'CLASSIFY': ('🗂️', 'Jeux de tri'),
  'MEMORY': ('🧠', 'Memory'),
  'MAP': ('🗺️', 'Cartes à situer'),
  'COLORING': ('🎨', 'Coloriages'),
  'WORD_FLASH': ('⚡', 'Mots éclair'),
  'SCRAMBLE': ('🔤', 'Lettres mélangées'),
  'DICTATION': ('🎧', 'Dictées'),
  'UNJUMBLE': ('🧶', 'Phrases à démêler'),
  'FIND_MATCH': ('🔎', 'Trouver la correspondance'),
  'PICTURE_MATCH': ('🖼️', 'Image et mot'),
  'PICTURE_FIND': ('🖼️', 'Quelle image ?'),
  'WHEEL': ('🎡', 'Roues aléatoires'),
  'BOX': ('🎁', 'Boîtes à ouvrir'),
  'RANDOM_CARDS': ('🃏', 'Cartes aléatoires'),
  'ALIGN': ('📐', 'Points alignés'),
  'NUMBER_LINE': ('📏', 'Droites graduées'),
  'FRACTION_BAR': ('🍕', 'Fractions à colorier'),
  'COLUMN_OP': ('🧮', 'Opérations posées'),
  'WORD_HUNT': ('🔍', 'Chasses aux mots'),
  'CONJUGATION': ('📝', 'Tableaux de conjugaison'),
  'HOMOPHONE': ('👂', 'Homophones'),
  'ALPHA_ORDER': ('🔤', 'Ordre alphabétique'),
  'CLOCK': ('🕒', 'Lire l\'heure'),
  'MONEY': ('💶', 'Monnaie'),
};

/// Avatars proposés à la création d'un profil.
const avatars = ['🦊', '🐼', '🦁', '🐸', '🐙', '🦄', '🐯', '🐨', '🐧', '🦉'];

String avatarOf(Child child) => child.avatar ?? child.displayName.characters.first.toUpperCase();

extension on String {
  Iterable<String> get characters => runes.map(String.fromCharCode);
}

/// Toutes les leçons de l'enfant, en préparation comprises : le parent les vérifie avant les
/// révisions (tableau de bord).
final allLessonsProvider = FutureProvider.autoDispose.family<List<LessonSummary>, String>(
  (ref, childId) => ref.watch(apiProvider).lessons(childId: childId),
);
