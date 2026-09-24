import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/app/app.dart';
import 'package:ludifun/app/router.dart';
import 'package:ludifun/core/storage/credentials.dart';
import 'package:ludifun/features/capture/capture_controller.dart';
import 'package:ludifun/features/home/home_providers.dart';
import 'package:ludifun/features/parent/file_sharer.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../support/fake_server.dart';
import '../support/fakes.dart';

const parent = ParentCredentials(accessToken: 'a1', refreshToken: 'r1', email: 'parent@example.fr');
final now = DateTime.utc(2026, 9, 23, 17);

Map<String, Object?> child({int devices = 0, String name = 'Emma', String grade = 'CM1'}) => {
  'id': 'c1',
  'display_name': name,
  'grade': grade,
  'avatar': '🦊',
  'created_at': '2026-09-01T10:00:00Z',
  'devices': devices,
};

Map<String, Object?> week(String monday, int sessions, int minutes, double? average) => {
  'week_start': monday,
  'sessions': sessions,
  'minutes': minutes,
  'average_score': average,
};

/// Une semaine de révisions d'Emma, telle que la calcule l'API (étape 8).
final dashboard = {
  'child_id': 'c1',
  'timezone': 'Europe/Paris',
  'this_week': week('2026-09-21', 4, 37, 8.5),
  'lessons_added_this_week': 2,
  'activities_this_week': {'MCQ': 4, 'FLASHCARD': 2, 'FILL_BLANK': 6},
  'subjects': [
    {'subject': 'french', 'mastery': 86, 'color': 'green', 'notions': 6},
    {'subject': 'math', 'mastery': 72, 'color': 'orange', 'notions': 5},
    {'subject': 'history', 'mastery': 91, 'color': 'green', 'notions': 8},
  ],
  'to_strengthen': [
    {
      'knowledge_id': 'k1',
      'label': 'Comparaison des fractions',
      'lesson_id': 'l2',
      'lesson_title': 'Les fractions',
      'subject': 'math',
      'mastery': 40,
      'status': 'not_mastered',
      'next_review_at': '2026-09-24T08:00:00Z',
      'level': 2,
      'explanation': 'Des réussites, mais encore fragile.',
    },
    {
      'knowledge_id': 'k2',
      'label': 'Imparfait',
      'lesson_id': 'l3',
      'lesson_title': 'Le passé',
      'subject': 'french',
      'mastery': 100,
      'status': 'to_review',
      'next_review_at': '2026-09-25T08:00:00Z',
      'level': 3,
      'explanation': 'Reconnaît la bonne réponse, pas encore la retrouver seul.',
    },
  ],
  'reviews_due': 3,
  'weeks': [
    week('2026-08-31', 1, 8, 5.5),
    week('2026-09-07', 2, 15, 6.5),
    week('2026-09-14', 3, 24, 7.5),
    week('2026-09-21', 4, 37, 8.5),
  ],
  'trend': 'up',
};

Map<String, Object?> session(String id, String title, String startedAt, double score) => {
  'session_id': id,
  'lesson_id': 'l1',
  'lesson_title': title,
  'subject': 'history',
  'kind': 'first',
  'status': 'completed',
  'started_at': startedAt,
  'completed_at': startedAt,
  'minutes': 9,
  'score_on_10': score,
  'notions': [
    {'label': '1789', 'status': 'mastered'},
    {'label': 'États généraux', 'status': 'to_review'},
  ],
};

/// Feuille de partage simulée : garde les fichiers remis au parent.
class FakeSharer implements FileSharer {
  final shared = <({String filename, Uint8List bytes, String mimeType, String? subject})>[];

  @override
  Future<void> share({
    required String filename,
    required Uint8List bytes,
    required String mimeType,
    String? subject,
  }) async => shared.add((filename: filename, bytes: bytes, mimeType: mimeType, subject: subject));
}

void main() {
  late FakeServer server;
  late FakeSharer sharer;
  late Map<String, Object?> emmaChild;

  setUp(() {
    sharer = FakeSharer();
    emmaChild = child();
    server = FakeServer()
      ..on('GET /v1/children', (_) => (200, [emmaChild]))
      ..on('GET /v1/children/c1/dashboard', (r) {
        expect(r.queryParameters['weeks'], 4);
        return (200, dashboard);
      });
  });

  Future<ProviderContainer> launch(WidgetTester tester, [Credentials credentials = parent]) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 2.5;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          ...overridesFor(server, MemoryCredentialStore(credentials)),
          nowProvider.overrideWithValue(() => now),
          imagePickerProvider.overrideWithValue(FakeImagePicker(gallery: 1)),
          imageCompressorProvider.overrideWithValue(FakeCompressor()),
          fileSharerProvider.overrideWithValue(sharer),
        ],
        retry: noRetry,
        child: const LudifunApp(),
      ),
    );
    await tester.pumpAndSettle();
    return ProviderScope.containerOf(tester.element(find.byType(LudifunApp)));
  }

  Future<void> go(WidgetTester tester, ProviderContainer container, String location) async {
    container.read(routerProvider).go(location);
    await tester.pumpAndSettle();
  }

  Future<void> tap(WidgetTester tester, Finder finder) async {
    await tester.ensureVisible(finder);
    await tester.tap(finder);
    await tester.pumpAndSettle();
  }

  testWidgets('critère de l\'étape 12 : le parent suit une semaine de révisions d\'Emma', (
    tester,
  ) async {
    await launch(tester);
    expect(find.text('Emma · CM1'), findsOneWidget);
    await tap(tester, find.text('Emma · CM1'));

    // Cette semaine.
    expect(find.text('🦊 Emma · CM1'), findsOneWidget);
    expect(find.text('4'), findsOneWidget);
    expect(find.text('37'), findsOneWidget);
    expect(find.text('8,5 / 10'), findsOneWidget);
    expect(find.text('🔄 3 notions à revoir aujourd\'hui'), findsOneWidget);

    // Réussite par matière, dans l'ordre du programme, avec le pourcentage écrit.
    expect(find.text('📖 Français'), findsOneWidget);
    expect(find.text('86 %'), findsOneWidget);
    expect(find.text('72 %'), findsOneWidget);
    expect(find.text('91 %'), findsOneWidget);

    // À renforcer, progression, activités.
    expect(find.text('Comparaison des fractions'), findsOneWidget);
    expect(find.text('Des réussites, mais encore fragile. · Les fractions'), findsOneWidget);
    expect(find.text('Imparfait'), findsOneWidget);
    // Réussie à 100 % en QCM, mais pas encore retrouvée seule : le niveau, pas le pourcentage.
    expect(
      find.text('Reconnaît la bonne réponse, pas encore la retrouver seul. · Le passé'),
      findsOneWidget,
    );
    expect(find.text('100 %'), findsNothing);
    expect(find.bySemanticsLabel('Niveau 3 sur 5 : En cours d\'acquisition'), findsOneWidget);
    expect(find.text('Note moyenne par semaine · en progression ↗'), findsOneWidget);
    expect(
      find.bySemanticsLabel('Semaine du 21/9 : 4 séances, 37 min, 8,5 / 10 en moyenne'),
      findsOneWidget,
    );
    expect(find.text('🎮 Quiz 4'), findsOneWidget);
    expect(find.text('✍️ Textes à trous 6'), findsOneWidget);
    expect(find.text('🃏 Cartes 2'), findsOneWidget);

    // Définitions affichables telles quelles.
    await tap(tester, find.byTooltip('Comment lire ce tableau'));
    expect(find.textContaining('Réussite par matière : maîtrise actuelle'), findsOneWidget);
    await tester.tapAt(const Offset(10, 10));
    await tester.pumpAndSettle();

    // Écran P4 : historique paginé.
    server
      ..on('GET /v1/children/c1/history', (r) {
        final older = r.queryParameters['before'] != null;
        return (
          200,
          older
              ? {
                  'sessions': [session('s1', 'Les fractions', '2026-09-20T15:00:00Z', 6)],
                  'next_before': null,
                }
              : {
                  'sessions': [
                    session('s3', 'La Révolution française', '2026-09-23T15:05:00Z', 8.5),
                    session('s2', 'La Révolution française', '2026-09-22T16:00:00Z', 7),
                  ],
                  'next_before': '2026-09-22T16:00:00Z',
                },
        );
      })
      ..on(
        'GET /v1/children/c1/devices',
        (_) => (
          200,
          [
            {
              'id': 'd1',
              'name': 'Appareil Android',
              'created_at': '2026-09-01T10:00:00Z',
              'last_seen_at': '2026-09-23T15:05:00Z',
            },
          ],
        ),
      );
    await tap(tester, find.byTooltip('Historique et réglages'));
    expect(find.text('8,5 / 10'), findsOneWidget);
    expect(find.textContaining('aujourd\'hui à'), findsWidgets);
    expect(find.text('✓ 1789'), findsNWidgets(2));
    expect(find.text('⚠ États généraux'), findsNWidgets(2));
    await tap(tester, find.text('Voir les séances plus anciennes'));
    expect(find.text('📐 Les fractions'), findsNothing); // matière de la fausse séance : histoire
    expect(find.textContaining('Les fractions'), findsOneWidget);
    expect(find.text('Voir les séances plus anciennes'), findsNothing);

    // Appareil lié : délier après confirmation.
    expect(find.text('Appareil Android'), findsOneWidget);
    server.on('DELETE /v1/children/c1/devices/d1', (_) => (204, null));
    await tap(tester, find.text('Délier'));
    await tap(tester, find.widgetWithText(FilledButton, 'Délier'));
    expect(server.routes, contains('DELETE /v1/children/c1/devices/d1'));
  });

  testWidgets('ajouter un enfant (consentement), puis lier sa tablette par code ou QR', (
    tester,
  ) async {
    var linkedDevices = 0;
    server
      ..on('GET /v1/children', (_) => (200, <Object>[]))
      ..on('POST /v1/children', (r) {
        expect(r.data, {
          'display_name': 'Hugo',
          'grade': 'CE1',
          'avatar': '🐼',
          'parental_consent': true,
        });
        return (201, child(name: 'Hugo', grade: 'CE1'));
      })
      ..on(
        'POST /v1/children/c1/link-codes',
        (_) => (
          201,
          {
            'code': '482731',
            'qr': 'ludifun://lier/jeton-secret-128-bits',
            'expires_at': now.add(const Duration(minutes: 10)).toIso8601String(),
          },
        ),
      )
      ..on(
        'GET /v1/children/c1/devices',
        (_) => (
          200,
          [
            for (var i = 0; i < linkedDevices; i++)
              {
                'id': 'd$i',
                'name': null,
                'created_at': '2026-09-23T17:00:00Z',
                'last_seen_at': null,
              },
          ],
        ),
      );
    await launch(tester);
    await tap(tester, find.text('Ajouter un enfant'));

    await tester.enterText(find.byType(TextFormField), 'Hugo');
    await tap(tester, find.text('CE1'));
    await tap(tester, find.text('🐼'));
    await tap(tester, find.text('Créer le profil'));
    expect(
      find.text('Le consentement parental est nécessaire pour créer le profil.'),
      findsOneWidget,
    );
    expect(server.routes, isNot(contains('POST /v1/children')));
    await tap(tester, find.byType(CheckboxListTile));
    server.on('GET /v1/children', (_) => (200, [child(name: 'Hugo', grade: 'CE1')]));
    await tap(tester, find.text('Créer le profil'));

    // Code et QR code, avec le temps restant.
    expect(find.text('482 731'), findsOneWidget);
    expect(find.byType(QrImageView), findsOneWidget);
    final qr = tester.widget<QrImageView>(find.byType(QrImageView));
    expect(qr.semanticsLabel, 'QR code de liaison');
    expect(find.text('Valable encore 10 min 00 s · une seule utilisation'), findsOneWidget);
    expect(find.textContaining('Hugo'), findsWidgets);

    // La tablette saisit le code : l'écran le voit.
    linkedDevices = 1;
    await tester.pump(const Duration(seconds: 4));
    await tester.pumpAndSettle();
    expect(find.text('L\'appareil de Hugo est lié !'), findsOneWidget);
  });

  testWidgets('le parent photographie une leçon pour Emma', (tester) async {
    var polls = 0;
    server
      ..on('POST /v1/lessons', (r) {
        expect(r.queryParameters['child_id'], 'c1');
        return (202, {'id': 'l9', 'status': 'uploaded'});
      })
      ..on('GET /v1/lessons/l9', (r) {
        expect(r.queryParameters['child_id'], 'c1');
        return (
          200,
          {
            'id': 'l9',
            'status': polls++ < 1 ? 'reading' : 'ready',
            'failure_reason': null,
            'subject': 'history',
            'title': 'La Révolution française',
            'created_at': '2026-09-23T15:00:00Z',
            'steps': {'reading': 'done', 'analyzing': 'done', 'generating': 'done'},
            'knowledge': <Object>[],
            'can_retry': false,
          },
        );
      });
    final container = await launch(tester);
    await go(tester, container, Routes.childDashboard('c1'));
    await tap(tester, find.text('Ajouter une leçon pour Emma'));
    expect(find.text('📷 Photographier la leçon'), findsOneWidget);
    await tap(tester, find.text('Ajouter depuis la galerie'));
    await tester.tap(find.text('Analyser ma leçon'));
    for (var i = 0; i < 60 && find.text('Cette semaine').evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    await tester.pumpAndSettle();
    expect(find.text('Leçon prête : elle apparaît dans la mission du jour.'), findsOneWidget);
    expect(find.text('Cette semaine'), findsOneWidget);
  });

  testWidgets('mot de passe oublié, puis lien de l\'e-mail', (tester) async {
    server
      ..on('POST /v1/auth/password-reset', (r) {
        expect(r.data, {'email': 'parent@example.fr'});
        return (202, {'status': 'ok'});
      })
      ..on('POST /v1/auth/password-reset/confirm', (r) {
        expect(r.data, {'token': 'ldf_r_abc', 'new_password': 'un nouveau mot de passe'});
        return (204, null);
      });
    final container = await launch(tester, const NoCredentials());
    await tap(tester, find.text('Je suis un parent'));
    await tap(tester, find.text('Mot de passe oublié ?'));
    await tester.enterText(find.byType(TextFormField), 'parent@example.fr');
    await tap(tester, find.text('Recevoir le lien'));
    expect(find.textContaining('un lien vient d\'être envoyé'), findsOneWidget);

    // Le lien ludifun://app/parent/nouveau-mot-de-passe?jeton=… ouvre cet écran.
    await go(tester, container, '/parent/nouveau-mot-de-passe?jeton=ldf_r_abc');
    await tester.enterText(find.byType(TextFormField), 'court');
    await tap(tester, find.text('Changer mon mot de passe'));
    expect(find.text('Au moins 12 caractères.'), findsOneWidget);
    await tester.enterText(find.byType(TextFormField), 'un nouveau mot de passe');
    await tap(tester, find.text('Changer mon mot de passe'));
    expect(find.text('Votre mot de passe est changé. Vous pouvez vous connecter.'), findsOneWidget);
  });

  testWidgets('modifier le profil, supprimer l\'enfant, supprimer le compte', (tester) async {
    server
      ..on(
        'GET /v1/children/c1/history',
        (_) => (200, {'sessions': <Object>[], 'next_before': null}),
      )
      ..on('GET /v1/children/c1/devices', (_) => (200, <Object>[]))
      ..on('PATCH /v1/children/c1', (r) {
        expect(r.data, {'display_name': 'Emma', 'grade': 'CM2', 'avatar': '🦊'});
        emmaChild = child(grade: 'CM2');
        return (200, emmaChild);
      })
      ..on('DELETE /v1/children/c1', (_) => (204, null))
      ..on('DELETE /v1/parent', (_) => (204, null));
    final container = await launch(tester);
    await go(tester, container, Routes.childSettings('c1'));
    expect(find.text('Emma n\'a pas encore fait de séance.'), findsOneWidget);

    await tap(tester, find.text('Modifier le profil'));
    await tap(tester, find.text('CM2'));
    await tap(tester, find.text('Enregistrer'));
    expect(server.routes, contains('PATCH /v1/children/c1'));

    await tap(tester, find.text('Supprimer Emma et toutes ses données'));
    expect(find.text('Supprimer le profil de Emma ?'), findsOneWidget);
    await tap(tester, find.widgetWithText(FilledButton, 'Supprimer'));
    expect(server.routes, contains('DELETE /v1/children/c1'));
    expect(find.text('Mes enfants'), findsOneWidget);

    await tap(tester, find.byTooltip('Mon compte'));
    await tap(tester, find.text('Supprimer mon compte'));
    await tap(tester, find.widgetWithText(FilledButton, 'Supprimer définitivement'));
    expect(server.routes, contains('DELETE /v1/parent'));
    expect(find.text('Qui utilise cet appareil ?'), findsOneWidget);
  });

  testWidgets('compétences par leçon, avec ce qui manque encore', (tester) async {
    Map<String, Object?> level(int value, String label, String color) => {
      'value': value,
      'label': label,
      'color': color,
    };
    server.on(
      'GET /v1/children/c1/skills',
      (_) => (
        200,
        {
          'lessons': [
            {
              'lesson_id': 'l2',
              'title': 'Les fractions',
              'subject': 'math',
              'created_at': '2026-09-20T15:00:00Z',
              'skills': [
                {
                  'id': 'sk1',
                  'label': 'Comparer deux fractions de même dénominateur',
                  'verb': 'apply',
                  'importance': 5,
                  'level': level(3, 'En cours d\'acquisition', 'orange'),
                  'knowledge_ids': ['k2', 'k4'],
                },
              ],
              'notions': [
                {
                  'id': 'k1',
                  'label': 'Fraction',
                  'importance': 5,
                  'level': level(5, 'Très bien maîtrisée', 'green'),
                  'explanation': 'Maîtrisée et bien retenue dans le temps.',
                },
                {
                  'id': 'k2',
                  'label': 'Numérateur',
                  'importance': 5,
                  'level': level(4, 'Maîtrisée', 'green'),
                  'explanation': 'Maîtrisée : il reste à la garder en mémoire.',
                },
                {
                  'id': 'k4',
                  'label': 'Comparer des fractions',
                  'importance': 4,
                  'level': level(3, 'En cours d\'acquisition', 'orange'),
                  'explanation': 'Connaît la règle, doit encore s\'entraîner à l\'appliquer.',
                },
              ],
            },
          ],
        },
      ),
    );
    await launch(tester);
    await tap(tester, find.text('Emma · CM1'));
    await tap(tester, find.text('Compétences par leçon'));

    expect(find.text('Compétences · Emma'), findsOneWidget);
    expect(find.text('📐 Les fractions'), findsOneWidget);
    expect(find.text('Comparer deux fractions de même dénominateur'), findsOneWidget);
    expect(find.text('En cours d\'acquisition · Appliquer'), findsOneWidget);
    // Notion reliée à aucune compétence : regroupée à part.
    expect(find.text('Autres notions'), findsOneWidget);

    await tap(tester, find.text('Comparer deux fractions de même dénominateur'));
    expect(find.text('Numérateur'), findsOneWidget);
    expect(find.text('Connaît la règle, doit encore s\'entraîner à l\'appliquer.'), findsOneWidget);
    expect(find.text('Fraction'), findsNothing); // dans « Autres notions », encore fermé

    await tap(tester, find.byTooltip('Comment lire les niveaux'));
    expect(
      find.textContaining('« Maîtrisée » ne veut pas dire « réussit les QCM »'),
      findsOneWidget,
    );
  });

  testWidgets('exporter les données d\'Emma (RGPD)', (tester) async {
    final export = {
      'format': 'ludifun-export-v1',
      'child': {'display_name': 'Emma'},
      'lessons': <Object>[],
    };
    server
      ..on(
        'GET /v1/children/c1/history',
        (_) => (200, {'sessions': <Object>[], 'next_before': null}),
      )
      ..on('GET /v1/children/c1/devices', (_) => (200, <Object>[]))
      ..on(
        'GET /v1/children/c1/export',
        (_) => (200, export),
        headers: {'content-disposition': 'attachment; filename="ludifun-c1-2026-09-24.json"'},
      );
    final container = await launch(tester);
    await go(tester, container, Routes.childSettings('c1'));

    await tap(tester, find.text('Exporter les données de Emma'));
    final file = sharer.shared.single;
    expect(file.filename, 'ludifun-c1-2026-09-24.json');
    expect(file.mimeType, 'application/json');
    expect(file.subject, 'Données Ludifun de Emma');
    expect(jsonDecode(utf8.decode(file.bytes)), export);

    // Erreur du serveur : message, et le bouton redevient utilisable.
    server.on(
      'GET /v1/children/c1/export',
      (_) => FakeServer.error(404, 'child_not_found', 'Enfant introuvable.'),
    );
    await tap(tester, find.text('Exporter les données de Emma'));
    expect(find.text('Enfant introuvable.'), findsOneWidget);
    expect(sharer.shared, hasLength(1));
  });
}
