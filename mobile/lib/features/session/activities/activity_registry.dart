import 'package:flutter/widgets.dart';

import '../../../models/account.dart';
import 'alignment_view.dart';
import 'classify_view.dart';
import 'coloring_view.dart';
import 'dictation_view.dart';
import 'fill_blank_view.dart';
import 'flashcard_view.dart';
import 'fun_games_views.dart';
import 'map_view.dart';
import 'match_view.dart';
import 'math_games_views.dart';
import 'mcq_view.dart';
import 'memory_view.dart';
import 'open_question_view.dart';
import 'order_view.dart';
import 'picture_views.dart';
import 'speed_challenge_view.dart';
import 'spelling_views.dart';
import 'true_false_view.dart';
import 'word_games_views.dart';

typedef ActivitySubmit = void Function(Map<String, Object?> response);
typedef ActivityBuilder = Widget Function(Json payload, ActivitySubmit onSubmit);

/// §14.3 : un widget par type d'activité. Un type absent (serveur plus récent que
/// l'application) est sauté proprement par le contrôleur de séance.
final activityRegistry = <String, ActivityBuilder>{
  'MCQ': (payload, onSubmit) => McqView(payload: payload, onSubmit: onSubmit),
  'TRUE_FALSE': (payload, onSubmit) => TrueFalseView(payload: payload, onSubmit: onSubmit),
  'FILL_BLANK': (payload, onSubmit) => FillBlankView(payload: payload, onSubmit: onSubmit),
  'MATCH': (payload, onSubmit) => MatchView(payload: payload, onSubmit: onSubmit),
  'SPEED_CHALLENGE': (payload, onSubmit) =>
      SpeedChallengeView(payload: payload, onSubmit: onSubmit),
  'FLASHCARD': (payload, onSubmit) => FlashcardView(payload: payload, onSubmit: onSubmit),
  'OPEN_QUESTION': (payload, onSubmit) => OpenQuestionView(payload: payload, onSubmit: onSubmit),
  // Activités graphiques (étape 21)
  'ORDER': (payload, onSubmit) => OrderView(payload: payload, onSubmit: onSubmit),
  'TIMELINE': (payload, onSubmit) =>
      OrderView(payload: payload, onSubmit: onSubmit, timeline: true),
  'CLASSIFY': (payload, onSubmit) => ClassifyView(payload: payload, onSubmit: onSubmit),
  'MEMORY': (payload, onSubmit) => MemoryView(payload: payload, onSubmit: onSubmit),
  // Activités sur une figure (étape 22)
  'MAP': (payload, onSubmit) => MapView(payload: payload, onSubmit: onSubmit),
  'COLORING': (payload, onSubmit) => ColoringView(payload: payload, onSubmit: onSubmit),
  // Jeux d'orthographe : listes de mots à savoir écrire
  'WORD_FLASH': (payload, onSubmit) => WordFlashView(payload: payload, onSubmit: onSubmit),
  'SCRAMBLE': (payload, onSubmit) => ScrambleView(payload: payload, onSubmit: onSubmit),
  'DICTATION': (payload, onSubmit) => DictationView(payload: payload, onSubmit: onSubmit),
  // Jeux en plus (étape 26)
  'UNJUMBLE': (payload, onSubmit) => UnjumbleView(payload: payload, onSubmit: onSubmit),
  'FIND_MATCH': (payload, onSubmit) => FindMatchView(payload: payload, onSubmit: onSubmit),
  'WHEEL': (payload, onSubmit) => WheelView(payload: payload, onSubmit: onSubmit),
  'BOX': (payload, onSubmit) => BoxView(payload: payload, onSubmit: onSubmit),
  'RANDOM_CARDS': (payload, onSubmit) => RandomCardsView(payload: payload, onSubmit: onSubmit),
  // Apprendre par l'image (étape 28)
  'PICTURE_MATCH': (payload, onSubmit) => PictureMatchView(payload: payload, onSubmit: onSubmit),
  'PICTURE_FIND': (payload, onSubmit) => PictureFindView(payload: payload, onSubmit: onSubmit),
  // Géométrie : figure dessinée à partir des coordonnées du serveur
  'ALIGN': (payload, onSubmit) => AlignmentView(payload: payload, onSubmit: onSubmit),
  // Jeux de maths calculés par le serveur
  'NUMBER_LINE': (payload, onSubmit) => NumberLineView(payload: payload, onSubmit: onSubmit),
  'FRACTION_BAR': (payload, onSubmit) => FractionBarView(payload: payload, onSubmit: onSubmit),
  'COLUMN_OP': (payload, onSubmit) => ColumnOperationView(payload: payload, onSubmit: onSubmit),
  // Jeux calculés pour toutes les matières
  'WORD_HUNT': (payload, onSubmit) => WordHuntView(payload: payload, onSubmit: onSubmit),
  'CONJUGATION': (payload, onSubmit) => ConjugationView(payload: payload, onSubmit: onSubmit),
  'HOMOPHONE': (payload, onSubmit) => HomophoneView(payload: payload, onSubmit: onSubmit),
};

/// Élément `{id, text}` d'une liste de la charge utile.
typedef Choice = ({String id, String text});

List<Choice> choicesOf(Object? list) => [
  for (final c in list as List<dynamic>)
    (id: (c as Json)['id'] as String, text: c['text'] as String),
];
