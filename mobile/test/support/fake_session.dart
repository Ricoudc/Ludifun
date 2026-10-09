import 'package:dio/dio.dart';

import 'fake_server.dart';

/// Une activité de la fausse séance : charge utile publique et bonne réponse.
class FakeItem {
  FakeItem(this.id, this.type, this.payload, this.expected, {this.block = 'core', this.daily});

  final String id;
  final String type;
  final Map<String, Object?> payload;
  final Map<String, Object?> expected;
  final String block;

  /// Nom du jeu du jour si c'est lui.
  final String? daily;
  Map<String, Object?>? answer;
}

/// Séance simulée côté serveur : notation, reprise des erreurs, bilan.
class FakeSessionBackend {
  FakeSessionBackend(this.server, this.id, this.items, {this.replay = const []}) {
    server
      ..on('GET /v1/sessions/$id', (_) => (200, sessionJson()))
      ..on('POST /v1/sessions/$id/attempts', _attempt)
      ..on('POST /v1/sessions/$id/replay', (_) {
        if (!replayServed) {
          items.addAll(replay);
          replayServed = true;
        }
        return (
          200,
          {
            'items': [for (final i in replay) itemJson(i)],
          },
        );
      })
      ..on('POST /v1/sessions/$id/complete', (_) {
        completed++;
        return (200, report);
      });
    for (final item in [...items, ...replay]) {
      server.on('POST /v1/sessions/$id/items/${item.id}/help', (_) {
        final level = (helpLevels[item.id] ?? 0) + 1;
        helpLevels[item.id] = level;
        return (200, helpSteps[level - 1]);
      });
    }
  }

  /// Aide demandée par activité (« Je n'ai pas compris »).
  final helpLevels = <String, int>{};

  static const helpSteps = [
    {
      'level': 1,
      'kind': 'hint',
      'title': '💡 Un indice',
      'text': 'Pense à la prise de la Bastille.',
      'lines': <String>[],
      'last': false,
    },
    {
      'level': 2,
      'kind': 'reminder',
      'title': '📖 Rappel de la leçon',
      'text': 'La Révolution commence l\'année des États généraux.',
      'lines': <String>[],
      'last': false,
    },
    {
      'level': 4,
      'kind': 'steps',
      'title': '🪜 Étape par étape',
      'text': 'Suis ces étapes :',
      'lines': ['Retrouve le siècle.', 'Retrouve la décennie.'],
      'last': false,
    },
    {
      'level': 5,
      'kind': 'answer',
      'title': '✅ La réponse',
      'text': '1789',
      'lines': ['En 1789, le peuple conteste le pouvoir du roi.'],
      'last': true,
    },
  ];

  final FakeServer server;
  final String id;
  final List<FakeItem> items;
  final List<FakeItem> replay;
  bool replayServed = false;
  int completed = 0;
  final durations = <int?>[];

  static const report = {
    'session_id': 's1',
    'score_on_10': 7.5,
    'counts': {'mastered': 2, 'to_review': 1, 'not_mastered': 0},
    'knowledge': [
      {
        'id': 'k3',
        'label': 'États généraux',
        'status': 'to_review',
        'session_rate': 0.6,
        'mastery': 60,
        'level': 3,
        'previous_level': 3,
        'explanation': 'Souvent réussie, avec encore quelques erreurs.',
      },
      {
        'id': 'k1',
        'label': '1789',
        'status': 'mastered',
        'session_rate': 1.0,
        'mastery': 90,
        'level': 4,
        'previous_level': 2,
        'explanation': 'Maîtrisée : il reste à la garder en mémoire.',
      },
      {'id': 'k2', 'label': 'Louis XVI', 'status': 'mastered', 'session_rate': 1.0, 'mastery': 90},
    ],
    'next_review_at': '2026-09-24T15:00:00Z',
    'lesson_mastered': false,
    'can_review_errors': true,
  };

  Map<String, Object?> itemJson(FakeItem item) => {
    'id': item.id,
    'position': items.indexOf(item),
    'block': item.block,
    'type': item.type,
    'difficulty': 1,
    'knowledge_ids': ['k1'],
    'payload': item.payload,
    'daily': item.daily,
    'help_available': !{'MATCH', 'SPEED_CHALLENGE'}.contains(item.type),
    'attempt': switch (item.answer) {
      null => null,
      {'skipped': true} => {'result': 'skipped', 'score': 0},
      final a => {'result': _correct(item, a) ? 'correct' : 'incorrect', 'score': 1},
    },
  };

  Map<String, Object?> sessionJson() => {
    'id': id,
    'lesson_id': 'l1',
    'kind': 'first',
    'status': completed > 0 ? 'completed' : 'active',
    'objective': 'Connaître les grandes dates de la Révolution',
    'estimated_duration_min': 6,
    'express': false,
    'items': [for (final i in items) itemJson(i)],
    'score_on_10': null,
  };

  static bool _correct(FakeItem item, Map<String, Object?> answer) =>
      answer.toString() == item.expected.toString();

  Reply _attempt(RequestOptions r) {
    final body = r.data as Map<String, dynamic>;
    final item = items.firstWhere((i) => i.id == body['item_id']);
    if (item.answer != null) return FakeServer.error(409, 'already_answered', 'Déjà répondu.');
    final response = (body['response'] as Map<String, dynamic>).cast<String, Object?>();
    item.answer = response;
    durations.add(body['duration_ms'] as int?);
    if (response['skipped'] == true) {
      return (200, {'item_id': item.id, 'result': 'skipped', 'score': 0, 'correct_answer': null});
    }
    final ok = _correct(item, response);
    return (
      200,
      {
        'item_id': item.id,
        'result': ok ? 'correct' : 'incorrect',
        'score': ok ? 1 : 0,
        'correct_answer': '1789',
        'tip': '1789 = début de la Révolution française.',
        'explanation': 'En 1789, le peuple conteste le pouvoir du roi.',
        'details': <Object>[],
      },
    );
  }
}

FakeItem mcq(String id, {String block = 'core'}) => FakeItem(
  id,
  'MCQ',
  {
    'prompt': 'En quelle année commence la Révolution française ?',
    'choices': [
      {'id': 'a', 'text': '1492'},
      {'id': 'b', 'text': '1789'},
      {'id': 'c', 'text': '1914'},
    ],
  },
  {'choice_id': 'b'},
  block: block,
);

FakeItem trueFalse(String id) => FakeItem(
  id,
  'TRUE_FALSE',
  {'statement': 'Louis XVI réunit les États généraux en 1789.'},
  {'value': true},
  block: 'warmup',
);
