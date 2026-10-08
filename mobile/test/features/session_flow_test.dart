import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/app/app.dart';
import 'package:ludifun/app/router.dart';
import 'package:ludifun/core/storage/credentials.dart';
import 'package:ludifun/features/session/session_controller.dart';

import '../support/fake_server.dart';
import '../support/fake_session.dart';
import '../support/screenshots.dart';

const child = ChildCredentials(deviceToken: 'ldf_d_x', childId: 'c1', displayName: 'Emma');

/// Critère de l'étape 11 : une séance complète jouée de bout en bout.
void main() {
  late FakeServer server;
  late DateTime clock;

  setUp(() {
    clock = DateTime(2026, 9, 23, 17);
    server = FakeServer()
      ..on('GET /v1/me', (_) => (200, emma))
      ..on('GET /v1/me/mission', (_) => (200, {'lesson': null}))
      ..on('GET /v1/lessons', (_) => (200, <Object>[]));
  });

  Future<void> open(WidgetTester tester, String sessionId) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.5;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...overridesFor(server, MemoryCredentialStore(child)),
          stopwatchProvider.overrideWithValue(() => clock),
        ],
        retry: noRetry,
        child: const LudifunApp(),
      ),
    );
    await tester.pumpAndSettle();
    ProviderScope.containerOf(tester.element(find.byType(LudifunApp)))
        .read(routerProvider)
        .go(Routes.session(sessionId));
    await tester.pumpAndSettle();
  }

  Future<void> tapAndSettle(WidgetTester tester, String text) async {
    await tester.tap(find.text(text));
    await tester.pumpAndSettle();
  }

  testWidgets('jeu → correction → reprise des erreurs → bilan → revoir mes erreurs', (
    tester,
  ) async {
    final backend = FakeSessionBackend(
      server,
      's1',
      [trueFalse('i1'), mcq('i2')],
      replay: [mcq('i3', block: 'replay')],
    );
    server.on(
      'POST /v1/sessions/s1/errors-session',
      (_) => (201, FakeSessionBackend(server, 's2', [mcq('e1')]).sessionJson()),
    );
    await open(tester, 's1');

    // Écran 5 : première question, compteur des activités principales.
    expect(find.text('Question 1 / 2'), findsOneWidget);
    expect(find.text('Louis XVI réunit les États généraux en 1789.'), findsOneWidget);
    await shot(tester, 's01_vrai_faux');
    clock = clock.add(const Duration(seconds: 7));
    await tapAndSettle(tester, '❌ Faux');

    // Écran 6 : correction bienveillante, avec l'astuce.
    expect(find.text('❌ Pas tout à fait !'), findsOneWidget);
    expect(find.textContaining('La bonne réponse est'), findsOneWidget);
    expect(
      find.text('💡 Astuce pour retenir : 1789 = début de la Révolution française.'),
      findsOneWidget,
    );
    await shot(tester, 's02_correction_faux');
    expect(backend.durations, [7000]);
    await tapAndSettle(tester, 'Continuer');

    expect(find.text('Question 2 / 2'), findsOneWidget);
    await shot(tester, 's03_qcm');
    await tapAndSettle(tester, '1789');
    expect(find.text('✅ Bravo !'), findsOneWidget);
    expect(find.textContaining('La bonne réponse est'), findsNothing);
    expect(find.text('En 1789, le peuple conteste le pouvoir du roi.'), findsOneWidget);
    await tapAndSettle(tester, 'Continuer');

    // Reprise des erreurs, avec son propre bandeau.
    expect(find.text('🔄 Reprise des erreurs 1 / 1'), findsOneWidget);
    await shot(tester, 's04_reprise');
    await tapAndSettle(tester, '1789');
    await tapAndSettle(tester, 'Continuer');

    // Écran 7 : bilan.
    expect(backend.completed, 1);
    expect(find.text('🎉 Révision terminée !'), findsOneWidget);
    expect(find.text('7,5 / 10'), findsOneWidget);
    expect(find.text('✅ 2 notions maîtrisées'), findsOneWidget);
    expect(find.text('🟠 1 notion à revoir'), findsOneWidget);
    expect(find.text('⚠ États généraux'), findsOneWidget);
    expect(find.text('✓ 1789'), findsOneWidget);
    // Seule la notion qui a gagné un niveau est citée dans « Tu as progressé ».
    expect(find.text('⬆️ Tu as progressé :'), findsOneWidget);
    expect(find.text('1789 · maîtrisée'), findsOneWidget);
    expect(find.textContaining('États généraux ·'), findsNothing);
    expect(find.text('📅 Prochaine révision : jeudi 24 septembre'), findsOneWidget);
    await shot(tester, 's05_bilan');

    // Étape 18 : un toucher pour dire si la séance a plu.
    Object? feedback;
    server.on('POST /v1/feedback', (r) {
      feedback = r.data;
      return (201, {'id': 'f1'});
    });
    expect(find.text('Tu as aimé cette séance ?'), findsOneWidget);
    await tester.ensureVisible(find.text('😍'));
    await tapAndSettle(tester, '😍');
    expect(feedback, {'rating': 5, 'screen': 'report', 'session_id': 's1'});
    expect(find.text('Merci ! 💜'), findsOneWidget);
    expect(find.text('😕'), findsNothing);

    // « Revoir mes erreurs » : une nouvelle séance courte.
    await tapAndSettle(tester, 'Revoir mes erreurs');
    expect(find.text('Question 1 / 1'), findsOneWidget);
    expect(server.routes, contains('GET /v1/sessions/s2'));
  });

  testWidgets('étape 20 : étapes de la mission, puis XP et badges au bilan', (tester) async {
    final backend = FakeSessionBackend(server, 's1', [mcq('i1', block: 'warmup'), mcq('i2')]);
    server.on('POST /v1/sessions/s1/complete', (_) {
      backend.completed++;
      return (
        200,
        {
          ...FakeSessionBackend.report,
          'rewards': {
            'xp': 27,
            'lines': [
              {'label': 'Séance terminée', 'xp': 10},
              {'label': 'Activités faites', 'xp': 2},
              {'label': 'Notions enfin réussies', 'xp': 10},
              {'label': 'Régularité', 'xp': 5},
            ],
            'message': '🏆 Tu as réussi une notion qui te posait problème : États généraux !',
            'new_badges': [
              {
                'code': 'comeback',
                'emoji': '🏆',
                'title': 'Revanche',
                'how': 'Réussis une notion qui te posait problème.',
                'earned_at': '2026-09-23T17:00:00Z',
              },
            ],
            'progress': {
              'total_xp': 187,
              'level': 2,
              'level_start_xp': 100,
              'next_level_xp': 300,
              'streak_days': 2,
              'done_today': true,
              'badges': <Object>[],
            },
          },
        },
      );
    });
    await open(tester, 's1');
    expect(find.text('🚀 Étape 1 / 2 · Échauffement'), findsOneWidget);
    await tapAndSettle(tester, '1789');
    await tapAndSettle(tester, 'Continuer');
    expect(find.text('🚀 Étape 2 / 2 · Entraînement'), findsOneWidget);
    await tapAndSettle(tester, '1789');
    await tapAndSettle(tester, 'Continuer');

    expect(
      find.text('🏆 Tu as réussi une notion qui te posait problème : États généraux !'),
      findsOneWidget,
    );
    expect(find.text('⭐ +27 XP'), findsOneWidget);
    expect(find.text('Notions enfin réussies  +10'), findsOneWidget);
    expect(find.text('🔥 Série : 2 jours'), findsOneWidget);
    expect(find.text('Nouveau badge : Revanche !'), findsOneWidget);
  });

  testWidgets('reprise d\'une séance interrompue et pause confirmée', (tester) async {
    final first = trueFalse('i1')..answer = {'value': true};
    FakeSessionBackend(server, 's1', [first, mcq('i2')]);
    await open(tester, 's1');
    expect(find.text('Question 2 / 2'), findsOneWidget); // on reprend là où on s'était arrêté

    await tester.tap(find.byType(CloseButton));
    await tester.pumpAndSettle();
    expect(find.text('Tu veux faire une pause ?'), findsOneWidget);
    await tapAndSettle(tester, 'Continuer');
    expect(find.text('Question 2 / 2'), findsOneWidget);

    await tester.tap(find.byType(CloseButton));
    await tester.pumpAndSettle();
    await tapAndSettle(tester, 'Arrêter');
    expect(find.text('Bonjour Emma ! 👋'), findsOneWidget);
  });

  testWidgets('activité inconnue de cette version : sautée sans être notée', (tester) async {
    final backend = FakeSessionBackend(server, 's1', [
      FakeItem('x1', 'PUZZLE', {'pieces': <Object>[]}, {}),
      mcq('i2'),
    ]);
    await open(tester, 's1');
    expect(backend.items.first.answer, {'skipped': true});
    expect(find.text('Question 2 / 2'), findsOneWidget);
  });

  testWidgets('« Revoir mes erreurs » sans erreur à revoir', (tester) async {
    FakeSessionBackend(server, 's1', [mcq('i1')]);
    server.on(
      'POST /v1/sessions/s1/errors-session',
      (_) => FakeServer.error(409, 'no_errors', 'Aucune erreur à revoir : bravo !'),
    );
    await open(tester, 's1');
    await tapAndSettle(tester, '1789');
    await tapAndSettle(tester, 'Continuer');
    await tapAndSettle(tester, 'Revoir mes erreurs');
    expect(find.text('Aucune erreur à revoir : bravo !'), findsOneWidget);
    expect(find.text('🎉 Révision terminée !'), findsOneWidget);
  });

  testWidgets('« Je n\'ai pas compris » : une aide à la fois, la réponse en dernier', (
    tester,
  ) async {
    final backend = FakeSessionBackend(server, 's1', [mcq('i1')]);
    await open(tester, 's1');
    await tapAndSettle(tester, '❓ Je n\'ai pas compris');
    expect(find.text('💡 Un indice'), findsOneWidget);
    expect(find.text('Pense à la prise de la Bastille.'), findsOneWidget);
    await shot(tester, 's06_aide');
    expect(find.text('✅ La réponse'), findsNothing);

    await tapAndSettle(tester, 'Encore de l\'aide');
    expect(find.text('📖 Rappel de la leçon'), findsOneWidget);
    // Fermer puis rouvrir : les aides déjà vues restent, sans nouvel appel.
    await tapAndSettle(tester, 'J\'essaie !');
    await tapAndSettle(tester, '❓ Je n\'ai pas compris');
    expect(find.text('💡 Un indice'), findsOneWidget);
    expect(backend.helpLevels['i1'], 2);

    await tapAndSettle(tester, 'Encore de l\'aide');
    expect(find.text('1. Retrouve le siècle.'), findsOneWidget);
    await tester.ensureVisible(find.text('Encore de l\'aide'));
    await tapAndSettle(tester, 'Encore de l\'aide');
    expect(find.text('✅ La réponse'), findsOneWidget);
    expect(find.text('Encore de l\'aide'), findsNothing); // plus rien après la réponse
    await tester.ensureVisible(find.text('J\'essaie !'));
    await tapAndSettle(tester, 'J\'essaie !');

    await tapAndSettle(tester, '1789');
    expect(find.text('✅ Bravo !'), findsOneWidget); // l'aide ne change pas la correction
    expect(find.text('❓ Je n\'ai pas compris'), findsNothing);
  });

  testWidgets('question ouverte : réponse rédigée, points clés trouvés et manquants', (
    tester,
  ) async {
    final backend = FakeSessionBackend(server, 's1', [
      FakeItem('o1', 'OPEN_QUESTION', {
        'prompt': 'Explique pourquoi 5/8 est plus grand que 3/8.',
        'max_length': 600,
      }, {}),
    ]);
    server.on('POST /v1/sessions/s1/attempts', (r) {
      final response = (r.data as Map<String, dynamic>)['response'] as Map<String, dynamic>;
      backend.items.single.answer = {'text': response['text']};
      return (
        200,
        {
          'item_id': 'o1',
          'result': 'incorrect',
          'score': 0.33,
          'correct_answer': 'Même dénominateur : on compare les numérateurs, 5 > 3.',
          'tip': null,
          'explanation': 'C\'est un début : tu as vu que les dénominateurs sont égaux.',
          'details': [
            {'point': 'même dénominateur', 'found': true},
            {'point': 'on compare les numérateurs', 'found': false},
          ],
        },
      );
    });
    await open(tester, 's1');
    expect(find.text('Réponds avec tes mots'), findsOneWidget);
    await shot(tester, 's07_question_ouverte');
    final validate = find.widgetWithText(FilledButton, 'Valider');
    expect(tester.widget<FilledButton>(validate).onPressed, isNull); // rien d'écrit
    await tester.enterText(find.byType(TextField), 'Elles ont le même dénominateur.');
    await tester.pump();
    await tapAndSettle(tester, 'Valider');

    expect(backend.items.single.answer, {'text': 'Elles ont le même dénominateur.'});
    expect(find.text('❌ Pas tout à fait !'), findsOneWidget);
    expect(
      find.text('Une réponse possible : Même dénominateur : on compare les numérateurs, 5 > 3.'),
      findsOneWidget,
    );
    expect(find.text('même dénominateur'), findsOneWidget);
    expect(find.text('on compare les numérateurs (il manquait)'), findsOneWidget);
    expect(
      find.text('C\'est un début : tu as vu que les dénominateurs sont égaux.'),
      findsOneWidget,
    );
  });

  testWidgets('deux échecs : rappel de la règle, puis activité facile insérée', (tester) async {
    final backend = FakeSessionBackend(server, 's1', [mcq('i1'), mcq('i2'), trueFalse('i3')]);
    final remediation = FakeItem(
      'r1',
      'TRUE_FALSE',
      {'statement': 'La Révolution française commence en 1789.'},
      {'value': true},
      block: 'remediation',
    );
    final original = server.handlers['POST /v1/sessions/s1/attempts']!;
    server.on('POST /v1/sessions/s1/attempts', (r) async {
      final (status, body) = await original(r);
      final id = (r.data as Map<String, dynamic>)['item_id'];
      if (id != 'i2') return (status, body);
      backend.items.insert(2, remediation);
      return (
        status,
        {
          ...body! as Map<String, Object?>,
          'inserted_items': [
            {
              ...backend.itemJson(remediation),
              'intro': '📖 Rappel : la Révolution commence en 1789.',
            },
          ],
        },
      );
    });
    await open(tester, 's1');
    await tapAndSettle(tester, '1492');
    await tapAndSettle(tester, 'Continuer');
    await tapAndSettle(tester, '1492'); // deuxième échec
    await tapAndSettle(tester, 'Continuer');
    expect(find.text('📖 Rappel : la Révolution commence en 1789.'), findsOneWidget);
    await shot(tester, 's08_rappel');
    expect(find.text('Question 3 / 4'), findsOneWidget);
    await tapAndSettle(tester, '✅ Vrai');
    await tapAndSettle(tester, 'Continuer');
    expect(find.text('Question 4 / 4'), findsOneWidget);
    expect(find.textContaining('Rappel'), findsNothing);
  });

  testWidgets('réponses au hasard : une pause est proposée', (tester) async {
    FakeSessionBackend(server, 's1', [mcq('i1'), mcq('i2')]);
    final original = server.handlers['POST /v1/sessions/s1/attempts']!;
    server.on('POST /v1/sessions/s1/attempts', (r) async {
      final (status, body) = await original(r);
      return (
        status,
        {
          ...body! as Map<String, Object?>,
          'engagement_hint': {
            'kind': 'fast_guessing',
            'message': 'Tu vas très vite ! On fait une petite pause ?',
          },
        },
      );
    });
    await open(tester, 's1');
    await tapAndSettle(tester, '1492');
    expect(find.text('☕ Tu vas très vite ! On fait une petite pause ?'), findsOneWidget);
    await shot(tester, 's09_pause');
    await tapAndSettle(tester, 'Faire une pause');
    expect(find.text('Bonjour Emma ! 👋'), findsOneWidget);
  });

  for (final accept in [true, false]) {
    testWidgets('séance rapide et réussie : défis bonus ${accept ? 'acceptés' : 'refusés'}', (
      tester,
    ) async {
      final backend = FakeSessionBackend(server, 's1', [mcq('i1')]);
      final bonus = mcq('b1', block: 'bonus');
      server
        ..on(
          'POST /v1/sessions/s1/replay',
          (_) => (200, {'items': <Object>[], 'bonus_offer': true}),
        )
        ..on('POST /v1/sessions/s1/extend', (_) {
          backend.items.add(bonus);
          return (
            200,
            {
              'items': [backend.itemJson(bonus)],
            },
          );
        });
      await open(tester, 's1');
      await tapAndSettle(tester, '1789');
      await tapAndSettle(tester, 'Continuer');
      expect(find.text('Tu as été rapide et tu as tout réussi !'), findsOneWidget);
      await shot(tester, 's10_bonus');
      if (accept) {
        await tapAndSettle(tester, 'Oui, j\'y vais !');
        expect(find.text('🚀 Défi bonus 1 / 1'), findsOneWidget);
        await tapAndSettle(tester, '1789');
        await tapAndSettle(tester, 'Continuer');
      } else {
        await tapAndSettle(tester, 'Non, j\'ai fini');
        expect(server.routes, isNot(contains('POST /v1/sessions/s1/extend')));
      }
      expect(backend.completed, 1);
      expect(find.text('🎉 Révision terminée !'), findsOneWidget);
    });
  }

  testWidgets('séance déjà terminée', (tester) async {
    FakeSessionBackend(server, 's1', [mcq('i1')]).completed = 1;
    await open(tester, 's1');
    expect(find.text('Cette séance est déjà terminée. 👍'), findsOneWidget);
  });

  testWidgets('réseau coupé pendant la réponse : message, puis reprise', (tester) async {
    final backend = FakeSessionBackend(server, 's1', [mcq('i1')]);
    final attempt = server.handlers['POST /v1/sessions/s1/attempts']!;
    server.on('POST /v1/sessions/s1/attempts', (_) => throw const _Offline());
    await open(tester, 's1');
    await tapAndSettle(tester, '1789');
    expect(find.text('Pas de connexion. Vérifie Internet et réessaie.'), findsOneWidget);
    server.on('POST /v1/sessions/s1/attempts', attempt);
    await tapAndSettle(tester, 'Réessayer');
    expect(find.text('Question 1 / 1'), findsOneWidget);
    await tapAndSettle(tester, '1789');
    expect(find.text('✅ Bravo !'), findsOneWidget);
    expect(backend.items.single.answer, {'choice_id': 'b'});
  });
}

class _Offline implements Exception {
  const _Offline();
}
