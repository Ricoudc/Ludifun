import 'dart:convert';
import 'dart:typed_data';

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
import '../support/screenshots.dart';

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
              // Image de la notion validée par le parent (étape 28).
              'image': '/v1/lessons/l1/images/i2',
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
  PickedDocument? document; // fichier choisi dans le sélecteur (null : annulé)

  var clock = now; // horloge de l'affichage, avancée par certains tests

  setUp(() {
    clock = now;
    server = FakeServer()
      ..on('GET /v1/me', (_) => (200, emma))
      ..on('GET /v1/me/mission', (_) => (200, {'lesson': null}))
      ..on('GET /v1/lessons', (_) => (200, <Object>[]));
    picker = FakeImagePicker();
    document = null;
  });

  Future<ProviderContainer> launch(WidgetTester tester, MemoryCredentialStore store) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...overridesFor(server, store),
          imagePickerProvider.overrideWithValue(picker),
          imageCompressorProvider.overrideWithValue(FakeCompressor()),
          documentPickerProvider.overrideWithValue(() async => document),
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
    await shot(tester, 'e00_depart');
    await tester.tap(find.text('Je suis un enfant'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '482731');
    await tester.pumpAndSettle();
    await shot(tester, 'e01_code');
    expect(find.text('C\'est toi, Emma ?'), findsOneWidget);
    expect(store.credentials, isA<NoCredentials>());
    await tester.tap(find.text('Oui, c\'est moi !'));
    await tester.pumpAndSettle();

    // Écran 1 : rien à réviser, aucune leçon.
    expect(find.text('Bonjour Emma ! 👋'), findsOneWidget);
    expect(find.text('🎉 Tout est à jour ! Photographie une nouvelle leçon.'), findsOneWidget);
    expect(find.text('Photographie ta première leçon !'), findsOneWidget);
    await shot(tester, 'e02_accueil_vide');

    // Écran 2 : deux pages de la galerie et une photo, puis la photo passe en premier.
    await tester.tap(find.text('Nouvelle leçon'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Pose le cahier à plat'), findsOneWidget);
    expect(find.textContaining('sans ton nom ni ton visage'), findsOneWidget);
    await shot(tester, 'e03_photo_vide');
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
    await shot(tester, 'e04_photos');

    // Envoi : pages compressées sur le téléphone, dans l'ordre choisi.
    var polls = 0;
    const progression = ['uploaded', 'reading', 'analyzing', 'generating', 'ready'];
    server
      ..on('POST /v1/lessons', (_) => (202, {'id': 'l1', 'status': 'uploaded'}))
      ..on('GET /v1/lessons/l1', (_) {
        final status = progression[(polls++).clamp(0, progression.length - 1)];
        return (
          200,
          lessonJson(status)
            // Image validée par le parent : montrée avec la leçon.
            ..['image'] = status == 'ready'
                ? {'url': '/v1/lessons/l1/image', 'alt': 'La prise de la Bastille'}
                : null,
        );
      })
      ..on('GET /v1/lessons/l1/image', (_) => (200, tinyPng))
      ..on('GET /v1/lessons/l1/images/i2', (_) => (200, tinyPng))
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
    await shot(tester, 'e05_analyse');
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
    expect(find.bySemanticsLabel('La prise de la Bastille'), findsOneWidget);
    // Compétences de la leçon et niveau de chaque notion, en étoiles.
    expect(find.text('Tu vas savoir :'), findsOneWidget);
    expect(find.text('Situer les grands événements de 1789'), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp('Niveau 1 sur 5 : Découverte')), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp('Niveau 2 sur 5 : Fragile')), findsOneWidget);
    expect(find.bySemanticsLabel(RegExp('Niveau 0 sur 5 : Jamais travaillée')), findsOneWidget);
    await tester.tap(find.text('États généraux'));
    await tester.pumpAndSettle();
    expect(find.text('Louis XVI réunit les États généraux en mai 1789.'), findsOneWidget);
    expect(server.routes, contains('GET /v1/lessons/l1/images/i2')); // l'image de la notion
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

  testWidgets('étape 30 : exercice MathALÉA ouvert dans l\'application, score envoyé une fois', (
    tester,
  ) async {
    Map<String, Object?> resource(String id, String provider, String kind, String url) => {
      'id': id,
      'provider': provider,
      'kind': kind,
      'title': 'Ressource $id',
      'url': url,
      'licence': 'Licence de $provider',
      'best': null,
    };
    final lesson = lessonJson('ready')
      ..['resources'] = [
        resource('r1', 'mathalea', 'exercise', 'https://coopmaths.fr/alea/?uuid=f0f0f&v=eleve'),
        resource('r2', 'lumni', 'video', 'https://www.lumni.fr/video/la-revolution'),
        // Site inconnu de cette version, ou adresse hors du site : jamais montrés.
        resource('r3', 'youtube', 'video', 'https://www.youtube.com/watch?v=x'),
        resource('r4', 'vikidia', 'quiz', 'https://vikidia.org.example.com/quiz'),
      ];
    final sent = <Object?>[];
    server
      ..on('GET /v1/lessons/l1', (_) => (200, lesson))
      ..on('POST /v1/lessons/l1/sessions', (_) => (201, session))
      ..on('POST /v1/lessons/l1/resources/r1/result', (r) {
        sent.add(r.data);
        return (200, {...resource('r1', 'mathalea', 'exercise', ''), 'best': r.data});
      });
    final container = await launch(tester, MemoryCredentialStore(child));
    container.read(routerProvider).go(Routes.lesson('l1'));
    await tester.pumpAndSettle();

    expect(find.text('🌐 Pour s\'entraîner autrement :'), findsOneWidget);
    expect(find.text('Ressource r1'), findsOneWidget);
    expect(find.text('Vidéo · Lumni'), findsOneWidget);
    expect(find.text('Ressource r3'), findsNothing);
    expect(find.text('Ressource r4'), findsNothing);
    await shot(tester, 'e08_lecon_ressources', height: 1600);

    await tester.ensureVisible(find.text('Ressource r1'));
    await tester.tap(find.text('Ressource r1'));
    await tester.pumpAndSettle();
    expect(find.text('Page : https://coopmaths.fr/alea/?uuid=f0f0f&v=eleve'), findsOneWidget);
    expect(find.text('Source : Licence de mathalea'), findsOneWidget);
    await shot(tester, 'e09_visionneuse');

    // Fin de l'exercice : le score part une seule fois, même si la page le renvoie.
    await tester.tap(find.text('Finir l\'exercice'));
    await tester.pumpAndSettle();
    expect(sent, [
      {'correct': 4, 'total': 5},
    ]);
    expect(find.text('👍 Score gardé : 4/5'), findsOneWidget);
    await tester.pump(const Duration(seconds: 5));
    await tester.pumpAndSettle();

    // Un lien vers un autre site n'est pas ouvert.
    await tester.tap(find.text('Lien externe'));
    await tester.pump();
    expect(
      find.text('Ce lien mène à un autre site (publicite.example.com) : il n\'est pas ouvert.'),
      findsOneWidget,
    );
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

    await shot(tester, 'e10_accueil_mission', height: 1300);
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

  testWidgets('leçon en PDF ou Word : le fichier part tel quel, puis l\'analyse', (tester) async {
    server
      ..on('POST /v1/lessons/document', (_) => (202, {'id': 'l1', 'status': 'uploaded'}))
      ..on('GET /v1/lessons/l1', (_) => (200, lessonJson('ready')));
    await launch(tester, MemoryCredentialStore(child));
    await tester.tap(find.text('Nouvelle leçon'));
    await tester.pumpAndSettle();

    // Annulé dans le sélecteur : rien n'est envoyé.
    await tester.tap(find.text('J\'ai la leçon en PDF ou Word'));
    await tester.pumpAndSettle();
    expect(server.routes, isNot(contains('POST /v1/lessons/document')));

    // Trop lourd : message, rien n'est envoyé.
    document = (name: 'gros.pdf', bytes: Uint8List(maxDocumentBytes + 1));
    await tester.tap(find.text('J\'ai la leçon en PDF ou Word'));
    await tester.pumpAndSettle();
    expect(find.text('Ce fichier est trop lourd (15 Mo au plus).'), findsOneWidget);
    expect(server.routes, isNot(contains('POST /v1/lessons/document')));

    document = (name: 'Revolution.docx', bytes: Uint8List.fromList(utf8.encode('PK leçon')));
    await tester.tap(find.text('J\'ai la leçon en PDF ou Word'));
    await advanceUntil(tester, find.text('C\'est prêt ! 🎉'));
    final sent = server.requests.indexWhere((r) => r.path == '/v1/lessons/document');
    final body = latin1.decode(server.bodies[sent]);
    expect(body, contains('name="document"; filename="Revolution.docx"'));
    expect(body, contains('wordprocessingml.document'));
    expect(bearer(server.requests[sent]), 'Bearer ldf_d_x');
    await advance(tester, const Duration(seconds: 2)); // fin de l'écran d'analyse
    await tester.pumpAndSettle();
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
    await shot(tester, 'e11_accueil_controle');
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
    await shot(tester, 'e12_accueil_xp');

    await tester.tap(find.text('🏅 Mes badges (1)'));
    await tester.pumpAndSettle();
    expect(find.text('Mes badges'), findsOneWidget);
    expect(find.text('Premier pas'), findsOneWidget);
    expect(find.text('Gagné !'), findsOneWidget);
    // Un badge pas encore gagné dit comment l'obtenir.
    expect(find.text('Réussis une notion qui te posait problème.'), findsOneWidget);
    expect(find.text('🔒'), findsOneWidget);
    await shot(tester, 'e13_badges');
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
    await shot(tester, 'e14_lecon_a_jour');
  });

  Map<String, Object?> homeworkJson({
    String status = 'ready',
    int shown = 1,
    List<(String, bool?)> attempts = const [],
    bool solutionAvailable = false,
  }) {
    const steps = [
      {
        'kind': 'task',
        'title': '🔎 Qu\'est-ce qu\'on cherche ?',
        'text': 'On cherche combien de billes il reste à Paul.',
      },
      {'kind': 'hint', 'title': '💡 Un indice', 'text': 'Paul en a-t-il plus ou moins après ?'},
      {'kind': 'method', 'title': '🧭 La méthode', 'text': 'Pose la soustraction.'},
    ];
    final finished = status == 'solved' || status == 'guided';
    return {
      'id': 'h1',
      'status': status,
      'statement': 'Paul a 24 billes. Il en donne 16. Combien lui en reste-t-il ?',
      'answer_kind': status == 'preparing' ? null : 'number',
      'steps': status == 'preparing' ? <Object>[] : steps.take(shown).toList(),
      'steps_left': status == 'preparing' ? 0 : steps.length - shown,
      'attempts': [
        for (final (text, correct) in attempts) {'text': text, 'correct': correct},
      ],
      'solution_available': solutionAvailable,
      'solution': finished ? ['24 − 16 = 8', 'Il reste 8 billes.'] : null,
      'answer': finished ? '8' : null,
      'check': status == 'solved' ? '8 + 16 = 24 : c\'est bon.' : null,
      'failure_message': null,
      'created_at': '2026-09-23T15:00:00Z',
    };
  }

  testWidgets('aide aux devoirs : étapes une par une, essais, puis correction guidée', (
    tester,
  ) async {
    var attempts = <(String, bool?)>[];
    var shown = 1;
    server
      ..on('POST /v1/homework/text', (r) {
        expect((r.data as Map)['text'], startsWith('Paul a 24 billes'));
        return (202, homeworkJson(status: 'preparing'));
      })
      ..on('GET /v1/homework/h1', (_) => (200, homeworkJson(shown: shown)))
      ..on('POST /v1/homework/h1/next-step', (_) => (200, homeworkJson(shown: ++shown)))
      ..on('POST /v1/homework/h1/attempts', (r) {
        attempts = [...attempts, ((r.data as Map)['text'] as String, false)];
        return (
          200,
          homeworkJson(shown: shown, attempts: attempts, solutionAvailable: attempts.length >= 2),
        );
      })
      ..on(
        'POST /v1/homework/h1/solution',
        (_) => (200, homeworkJson(status: 'guided', shown: 3, attempts: attempts)),
      );
    await launch(tester, MemoryCredentialStore(child));
    await tester.tap(find.text('Aide aux devoirs'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.byType(TextField),
      'Paul a 24 billes. Il en donne 16. Combien lui en reste-t-il ?',
    );
    await tester.pump();
    await tester.tap(find.text('C\'est parti !'));
    await tester.pumpAndSettle();

    // D'abord « Qu'est-ce qu'on cherche ? » ; pas de correction avant d'avoir essayé.
    expect(find.text('🔎 Qu\'est-ce qu\'on cherche ?'), findsOneWidget);
    expect(find.text('💡 Un indice'), findsNothing);
    expect(find.text('Voir la correction guidée'), findsNothing);
    await shot(tester, 'e15_devoirs');
    await tester.tap(find.text('Je veux un indice'));
    await tester.pumpAndSettle();
    expect(find.text('Paul en a-t-il plus ou moins après ?'), findsOneWidget);

    for (final wrong in ['40', '10']) {
      await tester.enterText(find.byType(TextField), wrong);
      await tester.pump();
      await tester.ensureVisible(find.text('Vérifier ma réponse'));
      await tester.tap(find.text('Vérifier ma réponse'));
      await tester.pumpAndSettle();
    }
    expect(find.textContaining('Pas encore !'), findsOneWidget);
    await tester.ensureVisible(find.text('Voir la correction guidée'));
    await tester.tap(find.text('Voir la correction guidée'));
    await tester.pumpAndSettle();
    expect(find.text('🧭 Correction guidée'), findsOneWidget);
    expect(find.text('• 24 − 16 = 8'), findsOneWidget);
    expect(find.text('La réponse : 8', findRichText: true), findsOneWidget);
    expect(find.text('Vérifier ma réponse'), findsNothing);
  });

  testWidgets('aide aux devoirs : la photo de l\'exercice, réussi seul', (tester) async {
    var solved = false;
    server
      ..on('POST /v1/homework', (_) => (202, homeworkJson(status: 'preparing')))
      ..on('GET /v1/homework/h1', (_) => (200, homeworkJson(status: solved ? 'solved' : 'ready')))
      ..on('POST /v1/homework/h1/attempts', (_) {
        solved = true;
        return (200, homeworkJson(status: 'solved', attempts: [('Il reste 8 billes', true)]));
      });
    await launch(tester, MemoryCredentialStore(child));
    await tester.tap(find.text('Aide aux devoirs'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Prendre l\'exercice en photo'));
    await tester.pumpAndSettle();
    expect(picker.cameraShots, 1);
    expect(server.routes, contains('POST /v1/homework'));
    await tester.enterText(find.byType(TextField), 'Il reste 8 billes');
    await tester.pump();
    await tester.tap(find.text('Vérifier ma réponse'));
    await tester.pumpAndSettle();
    expect(find.text('🎉 Bravo, c\'est juste !'), findsOneWidget);
    expect(find.text('✔️ Pour vérifier : 8 + 16 = 24 : c\'est bon.'), findsOneWidget);
  });

  testWidgets('aide aux devoirs : l\'exercice en PDF ou Word', (tester) async {
    server
      ..on('POST /v1/homework/document', (_) => (202, homeworkJson(status: 'preparing')))
      ..on('GET /v1/homework/h1', (_) => (200, homeworkJson(status: 'ready')));
    await launch(tester, MemoryCredentialStore(child));
    await tester.tap(find.text('Aide aux devoirs'));
    await tester.pumpAndSettle();
    document = (name: 'exercice.pdf', bytes: Uint8List.fromList(utf8.encode('%PDF-1.4')));
    await tester.tap(find.text('J\'ai l\'exercice en PDF ou Word'));
    await tester.pumpAndSettle();
    final sent = server.requests.indexWhere((r) => r.path == '/v1/homework/document');
    expect(sent, isNot(-1));
    expect(latin1.decode(server.bodies[sent]), contains('filename="exercice.pdf"'));
    expect(server.routes, contains('GET /v1/homework/h1'));
  });

  testWidgets('enseigne-moi : l\'enfant explique une notion à Ludi, puis le bilan', (tester) async {
    var answers = <String>[];
    Map<String, Object?> teachJson() {
      final finished = answers.length == 3;
      return {
        'id': 't1',
        'lesson_id': 'l1',
        'knowledge_id': 'k1',
        'label': 'Le pluriel des noms',
        'status': finished ? 'finished' : 'open',
        'messages': [
          for (final (i, answer) in answers.indexed) ...[
            {
              'speaker': 'ludi',
              'text': i == 0 ? 'Explique-moi « Le pluriel des noms » !' : 'Et pourquoi ?',
            },
            {'speaker': 'child', 'text': answer},
            {'speaker': 'ludi', 'text': 'Ah, d\'accord !'},
          ],
          if (!finished)
            {
              'speaker': 'ludi',
              'text': answers.isEmpty ? 'Explique-moi « Le pluriel des noms » !' : 'Et pourquoi ?',
            },
        ],
        'total': 2,
        'covered': finished ? 2 : null,
        'validated': finished ? true : null,
        'summary': finished ? 'Tu m\'as tout appris : 2 point(s) sur 2 !' : null,
        'created_at': '2026-09-23T15:00:00Z',
      };
    }

    server
      ..on('GET /v1/lessons/l1', (_) => (200, lessonJson('ready')))
      ..on('POST /v1/lessons/l1/teach', (_) => (201, teachJson()))
      ..on('GET /v1/teach/t1', (_) => (200, teachJson()))
      ..on('POST /v1/teach/t1/answers', (r) {
        answers = [...answers, (r.data as Map)['text'] as String];
        return (200, teachJson());
      });
    final container = await launch(tester, MemoryCredentialStore(child));
    container.read(routerProvider).go('/enfant/lecon/l1');
    await tester.pumpAndSettle();
    final teachMe = find.text('Enseigne-moi : explique ta leçon à Ludi');
    await tester.ensureVisible(teachMe);
    await tester.tap(teachMe);
    await tester.pumpAndSettle();
    expect(find.text('🧑‍🎓 Explique-moi « Le pluriel des noms » !'), findsOneWidget);
    await shot(tester, 'e16_enseigne_moi');

    for (final text in ['On ajoute un s.', 'Parce qu\'il y en a plusieurs.', 'Des chats.']) {
      await tester.enterText(find.byType(TextField), text);
      await tester.pump();
      await tester.ensureVisible(find.text('Expliquer à Ludi'));
      await tester.tap(find.text('Expliquer à Ludi'));
      await tester.pumpAndSettle();
      expect(find.text(text), findsOneWidget);
    }
    expect(answers, ['On ajoute un s.', 'Parce qu\'il y en a plusieurs.', 'Des chats.']);
    expect(find.text('Tu m\'as tout appris : 2 point(s) sur 2 !'), findsOneWidget);
    expect(find.text('⭐ Niveau « Expliquer » validé !'), findsOneWidget);
    expect(find.text('Expliquer à Ludi'), findsNothing);
    await tester.ensureVisible(find.text('Retour à la leçon'));
    await tester.tap(find.text('Retour à la leçon'));
    await tester.pumpAndSettle();
    expect(container.read(routerProvider).state.matchedLocation, '/enfant/lecon/l1');
  });

  testWidgets('mon cahier : relire une leçon et ses vidéos, puis un devoir, sans jeux', (
    tester,
  ) async {
    final sheet = {
      'lesson_id': 'l1',
      'title': 'La Révolution française',
      'subject': 'history',
      'grade': 'CM1',
      'objective': 'Connaître les grandes dates de la Révolution',
      'summary': 'En 1789, le peuple se révolte contre le roi.',
      'text': 'La Révolution française\nEn 1789, la France est en crise.',
      'image': null,
      'notions': [
        {
          'id': 'k1',
          'label': '1789',
          'statement': 'La Révolution française commence en 1789.',
          'explanation': 'Cette année-là, le peuple prend la Bastille.',
          'tip': 'Pense au 14 juillet, la fête nationale.',
          'card_front': 'En quelle année commence la Révolution ?',
          'card_back': '1789',
          'example': null,
          'importance': 5,
          'level': 3,
          'image': null,
        },
      ],
      'resources': [
        {
          'id': 'r2',
          'provider': 'lumni',
          'kind': 'video',
          'title': 'La Révolution en vidéo',
          'url': 'https://www.lumni.fr/video/la-revolution',
          'licence': 'Lumni',
          'best': null,
        },
      ],
    };
    server
      ..on(
        'GET /v1/lessons',
        (_) => (200, [lessonJson('ready'), lessonJson('failed', id: 'l2', failure: 'unreadable')]),
      )
      ..on('GET /v1/lessons/l1/sheet', (_) => (200, sheet))
      ..on(
        'GET /v1/homework',
        (_) => (
          200,
          {
            'homework': [
              {
                'id': 'h1',
                'created_at': '2026-09-23T15:00:00Z',
                'status': 'solved',
                'statement': 'Paul a 24 billes. Il en donne 16. Combien lui en reste-t-il ?',
                'steps_used': 0,
                'steps_total': 2,
                'attempts': 1,
                'solved_alone': true,
              },
            ],
            'next_before': null,
          },
        ),
      )
      ..on('GET /v1/homework/h1', (_) => (200, homeworkJson(status: 'solved')));
    final container = await launch(tester, MemoryCredentialStore(child));
    await tester.ensureVisible(find.text('Mon cahier'));
    await tester.tap(find.text('Mon cahier'));
    await tester.pumpAndSettle();

    // Seules les leçons prêtes, rangées par matière.
    expect(find.text('La Révolution française'), findsOneWidget);
    await tester.tap(find.text('La Révolution française'));
    await tester.pumpAndSettle();
    expect(find.text('La Révolution française commence en 1789.'), findsOneWidget);
    expect(find.text('💡 Astuce : Pense au 14 juillet, la fête nationale.'), findsOneWidget);
    expect(find.text('La Révolution en vidéo'), findsOneWidget);
    // La carte mémoire : la question, puis la réponse quand on la retourne.
    expect(find.text('✅ 1789'), findsNothing);
    final card = find.text('🃏 En quelle année commence la Révolution ?');
    await tester.ensureVisible(card);
    await tester.tap(card);
    await tester.pump();
    expect(find.text('✅ 1789'), findsOneWidget);
    await shot(tester, 'e17_cahier_fiche');
    // Aucune séance de jeux n'a été demandée.
    expect(server.routes.where((r) => r.contains('/sessions')), isEmpty);

    await tester.tap(find.byType(BackButton));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Mes devoirs'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Paul a 24 billes'), findsOneWidget);
    await tester.tap(find.textContaining('Paul a 24 billes'));
    await tester.pumpAndSettle();
    expect(find.text('🎉 Bravo, c\'est juste !'), findsOneWidget);
    await tester.tap(find.byType(BackButton));
    await tester.pumpAndSettle();
    expect(container.read(routerProvider).state.uri.toString(), Routes.notebookHomework);
    expect(find.textContaining('Paul a 24 billes'), findsOneWidget);
  });
}
