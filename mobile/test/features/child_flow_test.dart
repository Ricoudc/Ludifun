import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/app/app.dart';
import 'package:ludifun/app/router.dart';
import 'package:ludifun/core/storage/credentials.dart';
import 'package:ludifun/features/capture/capture_controller.dart';
import 'package:ludifun/features/home/home_providers.dart';

import '../support/fake_server.dart';
import '../support/fake_session.dart';
import '../support/fakes.dart';

const child = ChildCredentials(deviceToken: 'ldf_d_x', childId: 'c1', displayName: 'Emma');
final now = DateTime(2026, 9, 23, 17);

Map<String, Object?> lessonJson(
  String status, {
  String id = 'l1',
  String? failure,
  bool canRetry = false,
  String? nextReviewAt,
  bool due = false,
  bool mastered = false,
}) {
  const steps = ['reading', 'analyzing', 'generating'];
  final current = steps.indexOf(status);
  final ready = status == 'ready';
  return {
    'id': id,
    'status': status,
    'failure_reason': failure,
    'subject': ready ? 'history' : null,
    'title': ready ? 'La Révolution française' : null,
    'created_at': '2026-09-23T15:00:00Z',
    'next_review_at': nextReviewAt,
    'due': due,
    'mastered': mastered,
    'steps': status == 'failed'
        ? null
        : {
            for (final (i, step) in steps.indexed)
              step: ready || i < current ? 'done' : (i == current ? 'running' : 'pending'),
          },
    'failure_message': switch (failure) {
      'unreadable' => 'Je n\'arrive pas à lire ta photo. Reprends-la avec plus de lumière.',
      'ai_error' => 'Petit souci de mon côté, réessaie.',
      _ => null,
    },
    'grade': ready ? 'CM1' : null,
    'objective': ready ? 'Connaître les grandes dates de la Révolution' : null,
    'summary': null,
    'knowledge': ready
        ? [
            {
              'id': 'k1',
              'label': '1789',
              'statement': 'La Révolution française commence en 1789.',
              'importance': 5,
              'type': 'date',
              'level': 2,
            },
            {
              'id': 'k2',
              'label': 'États généraux',
              'statement': 'Louis XVI réunit les États généraux en mai 1789.',
              'importance': 4,
              'type': 'event',
              'source_excerpt': 'En mai 1789, Louis XVI réunit les États généraux à Versailles.',
              'source_page': 2,
            },
          ]
        : <Object>[],
    'skills': ready
        ? [
            {
              'id': 'sk1',
              'label': 'Situer les grands événements de 1789',
              'verb': 'recall',
              'importance': 5,
              'level': 1,
              'knowledge_ids': ['k1', 'k2'],
            },
          ]
        : <Object>[],
    'can_retry': canRetry,
  };
}

const session = {
  'id': 's1',
  'lesson_id': 'l1',
  'kind': 'first',
  'status': 'active',
  'objective': 'Connaître les grandes dates de la Révolution',
  'estimated_duration_min': 8,
  'express': false,
  'items': <Object>[],
  'score_on_10': null,
};

/// Fait défiler le temps (minuteries, animations sans fin) par petits pas.
Future<void> advance(WidgetTester tester, Duration total) async {
  const step = Duration(milliseconds: 100);
  for (var t = Duration.zero; t < total; t += step) {
    await tester.pump(step);
  }
}

/// Fait défiler le temps jusqu'à ce que [finder] apparaisse ; rend le temps écoulé.
Future<Duration> advanceUntil(
  WidgetTester tester,
  Finder finder, {
  Duration max = const Duration(seconds: 15),
}) async {
  const step = Duration(milliseconds: 100);
  var elapsed = Duration.zero;
  while (finder.evaluate().isEmpty) {
    if (elapsed > max) fail('$finder introuvable après $max');
    await tester.pump(step);
    elapsed += step;
  }
  return elapsed;
}

void main() {
  late FakeServer server;
  late FakeImagePicker picker;

  var clock = now; // horloge de l'affichage, avancée par certains tests

  setUp(() {
    clock = now;
    server = FakeServer()
      ..on('GET /v1/me', (_) => (200, emma))
      ..on('GET /v1/me/mission', (_) => (200, {'lesson': null}))
      ..on('GET /v1/lessons', (_) => (200, <Object>[]));
    picker = FakeImagePicker();
  });

  Future<ProviderContainer> launch(WidgetTester tester, MemoryCredentialStore store) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...overridesFor(server, store),
          imagePickerProvider.overrideWithValue(picker),
          imageCompressorProvider.overrideWithValue(FakeCompressor()),
          nowProvider.overrideWithValue(() => clock),
        ],
        retry: noRetry,
        child: const LudifunApp(),
      ),
    );
    await tester.pumpAndSettle();
    return ProviderScope.containerOf(tester.element(find.byType(LudifunApp)));
  }

  testWidgets('critère de l\'étape 10 : code → photo → analyse → résumé de la leçon', (
    tester,
  ) async {
    final store = MemoryCredentialStore();
    server.on(
      'POST /v1/link',
      (_) => (201, {'token': 'ldf_d_new', 'device_id': 'd1', 'child': emma}),
    );
    final container = await launch(tester, store);

    // Écran 0 : code, puis « C'est toi, Emma ? ».
    await tester.tap(find.text('Je suis un enfant'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '482731');
    await tester.pumpAndSettle();
    expect(find.text('C\'est toi, Emma ?'), findsOneWidget);
    expect(store.credentials, isA<NoCredentials>());
    await tester.tap(find.text('Oui, c\'est moi !'));
    await tester.pumpAndSettle();

    // Écran 1 : rien à réviser, aucune leçon.
    expect(find.text('Bonjour Emma ! 👋'), findsOneWidget);
    expect(find.text('🎉 Tout est à jour ! Photographie une nouvelle leçon.'), findsOneWidget);
    expect(find.text('Photographie ta première leçon !'), findsOneWidget);

    // Écran 2 : deux pages de la galerie et une photo, puis la photo passe en premier.
    await tester.tap(find.text('Nouvelle leçon'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Pose le cahier à plat'), findsOneWidget);
    expect(find.textContaining('sans ton nom ni ton visage'), findsOneWidget);
    await tester.tap(find.text('Ajouter depuis la galerie'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Prendre une photo'));
    await tester.pumpAndSettle();
    expect(picker.lastLimit, 6);
    final capture = container.read(captureProvider.notifier);
    expect(container.read(captureProvider).map((p) => p.path), [
      'page101.png',
      'page102.png',
      'page1.png',
    ]);
    capture.move(2, 0);
    await tester.pumpAndSettle();
    expect(find.bySemanticsLabel('Page 3'), findsOneWidget);

    // Envoi : pages compressées sur le téléphone, dans l'ordre choisi.
    var polls = 0;
    const progression = ['uploaded', 'reading', 'analyzing', 'generating', 'ready'];
    server
      ..on('POST /v1/lessons', (_) => (202, {'id': 'l1', 'status': 'uploaded'}))
      ..on(
        'GET /v1/lessons/l1',
        (_) => (200, lessonJson(progression[(polls++).clamp(0, progression.length - 1)])),
      )
      ..on('POST /v1/lessons/l1/sessions', (_) => (200, session));
    await tester.tap(find.text('Analyser ma leçon'));
    await advance(tester, const Duration(milliseconds: 200));
    final upload = server.requests.indexWhere((r) => r.path == '/v1/lessons' && r.method == 'POST');
    final body = latin1.decode(server.bodies[upload]);
    expect('jpeg:'.allMatches(body), hasLength(3));
    expect(RegExp(r'filename="(page\d\.jpg)"').allMatches(body).map((m) => m[1]), [
      'page1.jpg',
      'page2.jpg',
      'page3.jpg',
    ]);
    expect(bearer(server.requests[upload]), 'Bearer ldf_d_new');

    // Écran 3 : les étapes s'enchaînent, chacune visible au moins 800 ms.
    await advance(tester, const Duration(milliseconds: 500));
    expect(find.text('Lecture de ta leçon…'), findsOneWidget);
    expect(find.byIcon(Icons.check_circle), findsNothing);
    final waited = await advanceUntil(tester, find.text('C\'est prêt ! 🎉'));
    expect(waited, greaterThanOrEqualTo(const Duration(milliseconds: 1900))); // 3 × 800 ms
    expect(container.read(captureProvider), isEmpty); // photos effacées du téléphone
    await advance(tester, const Duration(seconds: 1));
    await tester.pumpAndSettle();

    // Écran 4 : résumé, durée de la vraie séance, notions à retenir.
    expect(find.text('🏛️ HISTOIRE · CM1'), findsOneWidget);
    expect(find.text('La Révolution française'), findsOneWidget);
    expect(find.text('🎯 Objectif : Connaître les grandes dates de la Révolution'), findsOneWidget);
    expect(find.text('⏱️ Durée estimée : 8 min'), findsOneWidget);
    // Compétences de la leçon et niveau de chaque notion, en étoiles.
    expect(find.text('Tu vas savoir :'), findsOneWidget);
    expect(find.text('Situer les grands événements de 1789'), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp('Niveau 1 sur 5 : Découverte')), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp('Niveau 2 sur 5 : Fragile')), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp('Niveau 0 sur 5 : Jamais travaillée')), findsOneWidget);
    await tester.tap(find.text('États généraux'));
    await tester.pumpAndSettle();
    expect(find.text('Louis XVI réunit les États généraux en mai 1789.'), findsOneWidget);
    // « Pourquoi cette notion ? » : la phrase de la leçon d'où elle vient (§116).
    expect(
      find.text('Pourquoi cette notion ? C\'est écrit dans ta leçon, page 2 :'),
      findsOneWidget,
    );
    expect(
      find.text('« En mai 1789, Louis XVI réunit les États généraux à Versailles. »'),
      findsOneWidget,
    );
    await tester.tapAt(const Offset(10, 10)); // ferme la fiche
    await tester.pumpAndSettle();

    // « Ce n'est pas le bon niveau ? »
    server.on('PATCH /v1/lessons/l1', (r) {
      expect(r.data, {'grade': 'CM2'});
      return (200, lessonJson('ready')..['grade'] = 'CM2');
    });
    final after = lessonJson('ready')..['grade'] = 'CM2';
    await tester.ensureVisible(find.text('Ce n\'est pas le bon niveau ?'));
    await tester.tap(find.text('Ce n\'est pas le bon niveau ?'));
    await tester.pumpAndSettle();
    server.on('GET /v1/lessons/l1', (_) => (200, after));
    await tester.tap(find.text('CM2'));
    await tester.pumpAndSettle();
    expect(find.text('🏛️ HISTOIRE · CM2'), findsOneWidget);

    FakeSessionBackend(server, 's1', [mcq('i1')]);
    await tester.tap(find.text('Commencer la révision'));
    await tester.pumpAndSettle();
    expect(find.text('Question 1 / 1'), findsOneWidget);
  });

  testWidgets('« Ce n\'est pas moi » : l\'appareil rend son jeton', (tester) async {
    final store = MemoryCredentialStore();
    server
      ..on('POST /v1/link', (_) => (201, {'token': 'ldf_d_new', 'device_id': 'd1', 'child': emma}))
      ..on('DELETE /v1/me/device', (_) => (204, null));
    await launch(tester, store);
    await tester.tap(find.text('Je suis un enfant'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '482731');
    await tester.pumpAndSettle();
    await tester.tap(find.text('Non'));
    await tester.pumpAndSettle();
    expect(find.text('Demande un nouveau code à ton parent, sur ton profil.'), findsOneWidget);
    final unlink = server.requests.last;
    expect('${unlink.method} ${unlink.path}', 'DELETE /v1/me/device');
    expect(bearer(unlink), 'Bearer ldf_d_new');
    expect(store.credentials, isA<NoCredentials>());
  });

  testWidgets('accueil : mission du jour et état de chaque leçon', (tester) async {
    server
      ..on(
        'GET /v1/me/mission',
        (_) => (
          200,
          {
            'lesson': {'id': 'l1', 'title': 'Les fractions', 'subject': 'math'},
            'reason': 'due',
            'estimated_minutes': 6,
          },
        ),
      )
      ..on(
        'GET /v1/lessons',
        (_) => (
          200,
          [
            lessonJson('ready', due: true),
            lessonJson('ready', id: 'l2', nextReviewAt: '2026-09-25T08:00:00Z'),
            lessonJson('ready', id: 'l3', mastered: true, nextReviewAt: '2026-10-07T08:00:00Z'),
            lessonJson('failed', id: 'l4', failure: 'unreadable'),
          ],
        ),
      )
      ..on('DELETE /v1/lessons/l4', (_) => (204, null));
    await launch(tester, MemoryCredentialStore(child));
    expect(find.text('📐 Les fractions · ⏱️ 6 min'), findsOneWidget);
    expect(find.text('à revoir aujourd\'hui 🔄'), findsOneWidget);
    expect(find.text('à revoir vendredi'), findsOneWidget);
    expect(find.text('maîtrisée ✓'), findsOneWidget);
    expect(find.text('Réessayer'), findsOneWidget);

    // Une photo ratée se retire par un appui long ; une leçon analysée, seul le parent la supprime.
    final failed = find.ancestor(of: find.text('Réessayer'), matching: find.byType(ListTile));
    await tester.ensureVisible(failed);
    await tester.longPress(failed);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Supprimer cette leçon'));
    await tester.pumpAndSettle();
    expect(server.routes, contains('DELETE /v1/lessons/l4'));
    expect(server.routes.where((r) => r.startsWith('DELETE')), ['DELETE /v1/lessons/l4']);
  });

  testWidgets('photo illisible : retour à l\'écran 2 avec les photos gardées', (tester) async {
    server
      ..on('POST /v1/lessons', (_) => (202, {'id': 'l1', 'status': 'uploaded'}))
      ..on('GET /v1/lessons/l1', (_) => (200, lessonJson('failed', failure: 'unreadable')))
      ..on('DELETE /v1/lessons/l1', (_) => (204, null));
    final container = await launch(tester, MemoryCredentialStore(child));
    await tester.tap(find.text('Nouvelle leçon'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ajouter depuis la galerie'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Analyser ma leçon'));
    await advance(tester, const Duration(seconds: 2));
    expect(
      find.text('Je n\'arrive pas à lire ta photo. Reprends-la avec plus de lumière.'),
      findsOneWidget,
    );
    await tester.tap(find.text('Reprendre la photo'));
    await tester.pumpAndSettle();
    expect(find.text('Analyser ma leçon'), findsOneWidget);
    expect(container.read(captureProvider), hasLength(2));
    expect(server.routes, contains('DELETE /v1/lessons/l1'));
  });

  testWidgets('serveur ralenti : une réponse en retard ne fige pas l\'écran d\'analyse', (
    tester,
  ) async {
    // Audit : la première réponse (« en cours ») arrivait après « prête » ; l'interrogation
    // étant arrêtée, l'écran tournait sans fin.
    var calls = 0;
    server.on('GET /v1/lessons/l1', (_) async {
      calls++;
      if (calls == 1) {
        await Future<void>.delayed(const Duration(seconds: 2));
        return (200, lessonJson('analyzing'));
      }
      return (200, lessonJson('ready'));
    });
    final container = await launch(tester, MemoryCredentialStore(child));
    container.read(routerProvider).go('/enfant/analyse/l1');
    await advanceUntil(
      tester,
      find.text('La Révolution française'),
      max: const Duration(seconds: 20),
    );
    await tester.pumpAndSettle();
  });

  testWidgets('photo que le téléphone ne sait pas lire : message, rien n\'est envoyé', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...overridesFor(server, MemoryCredentialStore(child)),
          imagePickerProvider.overrideWithValue(picker),
          imageCompressorProvider.overrideWithValue(BrokenCompressor()),
          nowProvider.overrideWithValue(() => clock),
        ],
        retry: noRetry,
        child: const LudifunApp(),
      ),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.text('Nouvelle leçon'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Ajouter depuis la galerie'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Analyser ma leçon'));
    await tester.pumpAndSettle();
    expect(
      find.text('Une photo n\'a pas pu être préparée. Retire-la et reprends-la.'),
      findsOneWidget,
    );
    expect(server.routes, isNot(contains('POST /v1/lessons')));
    expect(find.text('Analyser ma leçon'), findsOneWidget); // le bouton est de nouveau utilisable
  });

  testWidgets('erreur de l\'IA : relance sans nouvelle photo', (tester) async {
    var retried = false;
    server
      ..on(
        'GET /v1/lessons/l1',
        (_) => (
          200,
          retried ? lessonJson('ready') : lessonJson('failed', failure: 'ai_error', canRetry: true),
        ),
      )
      ..on('POST /v1/lessons/l1/retry', (_) {
        retried = true;
        return (202, {'id': 'l1', 'status': 'uploaded'});
      })
      ..on('POST /v1/lessons/l1/sessions', (_) => (200, session));
    final container = await launch(tester, MemoryCredentialStore(child));
    container.read(routerProvider).go('/enfant/analyse/l1');
    await advance(tester, const Duration(seconds: 1));
    expect(find.text('Petit souci de mon côté, réessaie.'), findsOneWidget);
    await tester.tap(find.text('Réessayer'));
    await advance(tester, const Duration(seconds: 5));
    await tester.pumpAndSettle();
    expect(find.text('La Révolution française'), findsOneWidget);
  });

  testWidgets('« Voir ce qui se passe » : l\'IA étape par étape, puis la raison de l\'échec', (
    tester,
  ) async {
    var failed = false;
    server.on(
      'GET /v1/lessons/l1',
      (_) => (
        200,
        failed
            ? {
                ...lessonJson('failed', failure: 'ai_error', canRetry: true),
                'diagnostics': {
                  'steps': [
                    {
                      'stage': 'lecture de la leçon',
                      'model': 'ollama/qwen2.5vl:7b',
                      'seconds': 900,
                      'status': 'error',
                      'message': 'Ollama n\'a pas répondu en 15 min (ReadTimeout)',
                    },
                  ],
                  'explanation': 'L\'IA a mis trop de temps à répondre.',
                },
              }
            : {
                ...lessonJson('reading'),
                'diagnostics': {
                  'steps': [
                    {
                      'stage': 'lecture de la leçon',
                      'model': 'ollama/qwen2.5vl:7b',
                      'seconds': 75,
                      'status': 'running',
                    },
                  ],
                  'explanation': null,
                },
              },
      ),
    );
    final container = await launch(tester, MemoryCredentialStore(child));
    container.read(routerProvider).go('/enfant/analyse/l1');
    await advance(tester, const Duration(seconds: 2));
    expect(find.text('Voir ce qui se passe'), findsOneWidget);
    expect(find.text('lecture de la leçon · ollama/qwen2.5vl:7b'), findsNothing); // replié
    await tester.tap(find.text('Voir ce qui se passe'));
    await advance(tester, const Duration(seconds: 1));
    expect(find.text('lecture de la leçon · ollama/qwen2.5vl:7b'), findsOneWidget);
    expect(find.text('depuis 1 min 15'), findsOneWidget);

    failed = true;
    await advance(tester, const Duration(seconds: 3));
    expect(find.text('Petit souci de mon côté, réessaie.'), findsOneWidget);
    expect(find.text('Pourquoi ? L\'IA a mis trop de temps à répondre.'), findsOneWidget);
    expect(find.text('Ollama n\'a pas répondu en 15 min (ReadTimeout)'), findsOneWidget);
    expect(find.text('15 min 00'), findsOneWidget);
  });

  testWidgets('analyse longue (IA de l\'ordinateur) : le temps écoulé et qu\'on peut fermer', (
    tester,
  ) async {
    server.on('GET /v1/lessons/l1', (_) => (200, lessonJson('reading')));
    final container = await launch(tester, MemoryCredentialStore(child));
    container.read(routerProvider).go('/enfant/analyse/l1');
    await advance(tester, const Duration(seconds: 2));
    expect(find.textContaining('min'), findsNothing); // attente courte : rien à expliquer
    clock = now.add(const Duration(minutes: 4));
    await advance(tester, const Duration(seconds: 2));
    expect(find.text('⏳ 4 min'), findsOneWidget);
    expect(find.textContaining('Tu peux fermer'), findsOneWidget);
  });

  testWidgets('coller le texte d\'une leçon au lieu de la photographier', (tester) async {
    const text =
        'La Révolution française. En 1789, la France est en crise : le roi manque d\'argent.';
    server
      ..on('POST /v1/lessons/text', (r) {
        expect(r.data, {'text': text});
        return (202, {'id': 'l1', 'status': 'uploaded'});
      })
      ..on('GET /v1/lessons/l1', (_) => (200, lessonJson('ready')))
      ..on('POST /v1/lessons/l1/sessions', (_) => (200, session));
    await launch(tester, MemoryCredentialStore(child));
    await tester.tap(find.text('Nouvelle leçon'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('J\'ai le texte de la leçon'));
    await tester.pumpAndSettle();
    expect(find.text('📋 Coller une leçon'), findsOneWidget);

    final analyze = find.widgetWithText(FilledButton, 'Analyser ma leçon');
    await tester.enterText(find.byType(TextField), 'Trop court');
    await tester.pump();
    expect(find.text('C\'est un peu court pour une leçon.'), findsOneWidget);
    expect(tester.widget<FilledButton>(analyze).onPressed, isNull);

    await tester.enterText(find.byType(TextField), '  $text  ');
    await tester.pump();
    await tester.tap(analyze);
    await advanceUntil(tester, find.text('C\'est prêt ! 🎉'));
    await advance(tester, const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(find.text('La Révolution française'), findsOneWidget);
  });

  testWidgets('« Peux-tu vérifier ? » : un mot mal lu, un mot illisible, puis l\'analyse reprend', (
    tester,
  ) async {
    var reviewed = false;
    Map<String, Object?>? sent;
    server
      ..on(
        'GET /v1/lessons/l1',
        (_) => (
          200,
          reviewed
              ? lessonJson('ready')
              : {
                  ...lessonJson('reading'),
                  'status': 'needs_review',
                  'steps': {'reading': 'done', 'analyzing': 'pending', 'generating': 'pending'},
                  'review': [
                    {
                      'id': 'r1',
                      'page_index': 0,
                      'read_text': 'Bastile',
                      'context': 'le peuple de Paris prend la Bastile, une prison',
                    },
                    {
                      'id': 'r2',
                      'page_index': 0,
                      'read_text': '[illisible]',
                      'context': 'le 5 mai 1789 à [illisible]',
                    },
                  ],
                },
        ),
      )
      ..on('POST /v1/lessons/l1/review', (r) {
        sent = (r.data as Map<String, dynamic>).cast<String, Object?>();
        reviewed = true;
        return (202, {'id': 'l1', 'status': 'uploaded'});
      })
      ..on('POST /v1/lessons/l1/sessions', (_) => (200, session));
    final container = await launch(tester, MemoryCredentialStore(child));
    container.read(routerProvider).go('/enfant/analyse/l1');
    await advanceUntil(tester, find.text('🔍 Peux-tu vérifier ?'));
    await advance(tester, const Duration(seconds: 1));
    expect(find.text('J\'ai lu « Bastile » ici :'), findsOneWidget);
    expect(find.text('Je n\'ai pas pu lire un mot ici :'), findsOneWidget);
    expect(find.text('✓ C\'est bien ça'), findsOneWidget); // pas pour un mot illisible

    final submit = find.widgetWithText(FilledButton, 'Continuer l\'analyse');
    await tester.ensureVisible(find.text('✏️ Je corrige'));
    await tester.tap(find.text('✏️ Je corrige'));
    await tester.pump();
    await tester.enterText(find.byType(TextField), 'Bastille');
    await tester.pump();
    expect(tester.widget<FilledButton>(submit).onPressed, isNull); // un passage sans réponse
    await tester.ensureVisible(find.text('🤷 Je ne sais pas').last);
    await tester.tap(find.text('🤷 Je ne sais pas').last);
    await tester.pump();
    await tester.ensureVisible(submit);
    await tester.tap(submit);
    await advanceUntil(tester, find.text('C\'est prêt ! 🎉'));
    expect(sent, {
      'answers': [
        {'item_id': 'r1', 'status': 'corrected', 'text': 'Bastille'},
        {'item_id': 'r2', 'status': 'unknown'},
      ],
    });
    await advance(tester, const Duration(seconds: 2));
    await tester.pumpAndSettle();
    expect(find.text('La Révolution française'), findsOneWidget);
  });

  testWidgets('mission du jour : l\'étape du plan avant un contrôle', (tester) async {
    server.on(
      'GET /v1/me/mission',
      (_) => (
        200,
        {
          'lesson': {'id': 'l1', 'title': 'Les fractions', 'subject': 'math'},
          'reason': 'exam',
          'estimated_minutes': 12,
          'exam': {
            'title': 'Contrôle de fractions',
            'exam_date': '2026-09-25',
            'focus': 'targeted',
            'focus_label': 'Exercices ciblés sur ce qui est fragile',
          },
          'daily_minutes': 15,
        },
      ),
    );
    await launch(tester, MemoryCredentialStore(child));
    expect(find.text('📅 Contrôle de fractions vendredi'), findsOneWidget);
    expect(find.text('Exercices ciblés sur ce qui est fragile'), findsOneWidget);
    expect(find.text('📐 Les fractions · ⏱️ 12 min'), findsOneWidget);
  });

  testWidgets('étape 20 : XP, niveau, série et badges sur l\'accueil', (tester) async {
    Map<String, Object?> badge(String code, String emoji, String title, String how, [String? at]) =>
        {'code': code, 'emoji': emoji, 'title': title, 'how': how, 'earned_at': at};
    server.on(
      'GET /v1/me/progress',
      (_) => (
        200,
        {
          'total_xp': 160,
          'level': 2,
          'level_start_xp': 100,
          'next_level_xp': 300,
          'streak_days': 4,
          'done_today': false,
          'badges': [
            badge(
              'first_session',
              '🌱',
              'Premier pas',
              'Termine ta première séance.',
              '2026-09-20T17:00:00Z',
            ),
            badge('comeback', '🏆', 'Revanche', 'Réussis une notion qui te posait problème.'),
          ],
        },
      ),
    );
    final container = await launch(tester, MemoryCredentialStore(child));
    expect(find.text('⭐ 160 XP · Niveau 2'), findsOneWidget);
    expect(find.text('🔥 Série : 4 jours'), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp('Encore 140 XP avant le niveau 3')), findsOneWidget);

    await tester.tap(find.text('🏅 Mes badges (1)'));
    await tester.pumpAndSettle();
    expect(find.text('Mes badges'), findsOneWidget);
    expect(find.text('Premier pas'), findsOneWidget);
    expect(find.text('Gagné !'), findsOneWidget);
    // Un badge pas encore gagné dit comment l'obtenir.
    expect(find.text('Réussis une notion qui te posait problème.'), findsOneWidget);
    expect(find.text('🔒'), findsOneWidget);
    expect(container.read(routerProvider).state.matchedLocation, Routes.badges);
  });

  testWidgets('accueil : une leçon à vérifier', (tester) async {
    server.on(
      'GET /v1/lessons',
      (_) => (
        200,
        [
          {...lessonJson('reading'), 'status': 'needs_review'},
        ],
      ),
    );
    await launch(tester, MemoryCredentialStore(child));
    expect(find.text('Un mot à vérifier'), findsOneWidget);
    expect(find.text('Vérifier'), findsOneWidget);
  });

  testWidgets('leçon à jour : pas de séance, date de la prochaine révision', (tester) async {
    server
      ..on(
        'GET /v1/lessons/l1',
        (_) => (200, lessonJson('ready', nextReviewAt: '2026-09-24T08:00:00Z')),
      )
      ..on(
        'POST /v1/lessons/l1/sessions',
        (_) => FakeServer.error(409, 'nothing_to_review', 'Tout est à jour.'),
      );
    final container = await launch(tester, MemoryCredentialStore(child));
    container.read(routerProvider).go('/enfant/lecon/l1');
    await tester.pumpAndSettle();
    expect(find.text('🎉 Tout est à jour pour cette leçon ! Reviens demain.'), findsOneWidget);
    expect(find.text('Commencer la révision'), findsNothing);
  });
}
