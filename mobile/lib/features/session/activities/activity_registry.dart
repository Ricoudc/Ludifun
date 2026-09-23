import 'package:flutter/widgets.dart';

import '../../../models/account.dart';
import 'fill_blank_view.dart';
import 'flashcard_view.dart';
import 'match_view.dart';
import 'mcq_view.dart';
import 'speed_challenge_view.dart';
import 'true_false_view.dart';

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
};

/// Élément `{id, text}` d'une liste de la charge utile.
typedef Choice = ({String id, String text});

List<Choice> choicesOf(Object? list) => [
  for (final c in list as List<dynamic>)
    (id: (c as Json)['id'] as String, text: c['text'] as String),
];
