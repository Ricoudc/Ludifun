import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/app/app.dart';
import 'package:ludifun/app/router.dart';
import 'package:ludifun/core/storage/credentials.dart';
import 'package:ludifun/features/session/session_controller.dart';

import '../support/fake_server.dart';
import '../support/fake_session.dart';

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
    clock = clock.add(const Duration(seconds: 7));
    await tapAndSettle(tester, '❌ Faux');

    // Écran 6 : correction bienveillante, avec l'astuce.
    expect(find.text('❌ Pas tout à fait !'), findsOneWidget);
    expect(find.textContaining('La bonne réponse est'), findsOneWidget);
    expect(
      find.text('💡 Astuce pour retenir : 1789 = début de la Révolution française.'),
      findsOneWidget,
    );
    expect(backend.durations, [7000]);
    await tapAndSettle(tester, 'Continuer');

    expect(find.text('Question 2 / 2'), findsOneWidget);
    await tapAndSettle(tester, '1789');
    expect(find.text('✅ Bravo !'), findsOneWidget);
    expect(find.textContaining('La bonne réponse est'), findsNothing);
    expect(find.text('En 1789, le peuple conteste le pouvoir du roi.'), findsOneWidget);
    await tapAndSettle(tester, 'Continuer');

    // Reprise des erreurs, avec son propre bandeau.
    expect(find.text('🔄 Reprise des erreurs 1 / 1'), findsOneWidget);
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

    // « Revoir mes erreurs » : une nouvelle séance courte.
    await tapAndSettle(tester, 'Revoir mes erreurs');
    expect(find.text('Question 1 / 1'), findsOneWidget);
    expect(server.routes, contains('GET /v1/sessions/s2'));
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
      FakeItem('x1', 'MEMORY', {'cards': <Object>[]}, {}),
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
