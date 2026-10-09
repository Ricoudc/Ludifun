import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/core/api/api_exception.dart';
import 'package:ludifun/core/session.dart';
import 'package:ludifun/core/storage/credentials.dart';

import '../support/fake_server.dart';

const parent = ParentCredentials(
  accessToken: 'old',
  refreshToken: 'r1',
  email: 'parent@example.fr',
);
const child = ChildCredentials(deviceToken: 'ldf_d_x', childId: 'c1', displayName: 'Emma');

Future<ProviderContainer> start(FakeServer server, MemoryCredentialStore store) async {
  final container = ProviderContainer(overrides: overridesFor(server, store), retry: noRetry);
  addTearDown(container.dispose);
  await container.read(sessionProvider.future);
  return container;
}

void main() {
  late FakeServer server;
  setUp(() => server = FakeServer());

  group('erreurs', () {
    test('le message de l\'API est affiché tel quel', () async {
      server.on(
        'POST /v1/link',
        (_) => FakeServer.error(400, 'invalid_link_code', 'Ce code ne marche pas.'),
      );
      final api = (await start(server, MemoryCredentialStore())).read(apiProvider);
      await expectLater(
        api.link(code: '123456'),
        throwsA(
          isA<ApiException>()
              .having((e) => e.code, 'code', 'invalid_link_code')
              .having((e) => e.status, 'status', 400)
              .having((e) => e.message, 'message', 'Ce code ne marche pas.')
              // Ancien serveur, sans catégorie : déduite du statut (§135).
              .having((e) => e.category, 'category', 'VALIDATION_ERROR'),
        ),
      );
    });

    test('la catégorie du §135 vient du serveur', () async {
      server.on(
        'GET /v1/me',
        (_) => (
          503,
          {
            'error': {
              'code': 'ai_budget_exhausted',
              'category': 'AI_ERROR',
              'message': 'Réessaie demain.',
            },
          },
        ),
      );
      final api = (await start(server, MemoryCredentialStore(child))).read(apiProvider);
      await expectLater(
        api.me(),
        throwsA(isA<ApiException>().having((e) => e.category, 'category', 'AI_ERROR')),
      );
    });

    test('sans réseau, un message compréhensible', () async {
      server.on('GET /v1/me', (_) => throw const SocketLikeException());
      final api = (await start(server, MemoryCredentialStore(child))).read(apiProvider);
      await expectLater(
        api.me(),
        throwsA(
          isA<ApiException>()
              .having((e) => e.code, 'code', 'network')
              .having((e) => e.category, 'category', 'NETWORK_ERROR'),
        ),
      );
    });

    test('une réponse inattendue ne montre pas de détail technique', () async {
      server.on('GET /v1/me', (_) => (502, '<html>Bad gateway</html>'));
      final api = (await start(server, MemoryCredentialStore(child))).read(apiProvider);
      await expectLater(
        api.me(),
        throwsA(
          isA<ApiException>()
              .having((e) => e.message, 'message', ApiException.unexpected)
              .having((e) => e.category, 'category', 'UNKNOWN_ERROR'),
        ),
      );
    });
  });

  group('jetons', () {
    test('chaque espace envoie son jeton, jamais sur les routes anonymes', () async {
      server
        ..on('GET /v1/me', (_) => (200, emma))
        ..on('POST /v1/auth/login', (_) => (200, tokens('a', 'r')));
      final api = (await start(server, MemoryCredentialStore(child))).read(apiProvider);
      await api.me();
      await api.login(email: 'parent@example.fr', password: 'x');
      expect(bearer(server.requests[0]), 'Bearer ldf_d_x');
      expect(bearer(server.requests[1]), isNull);
    });

    test('parent : jeton expiré → renouvelé une seule fois, requêtes rejouées', () async {
      final store = MemoryCredentialStore(parent);
      server
        ..on(
          'GET /v1/children',
          (r) => bearer(r) == 'Bearer new'
              ? (200, [emma])
              : FakeServer.error(401, 'unauthorized', 'Session expirée.'),
        )
        ..on('POST /v1/auth/refresh', (r) async {
          expect(r.data, {'refresh_token': 'r1'});
          return (200, tokens('new', 'r2'));
        });
      final container = await start(server, store);
      final api = container.read(apiProvider);

      final results = await Future.wait([api.children(), api.children()]);
      expect(results.map((list) => list.single.displayName), ['Emma', 'Emma']);
      expect(server.routes.where((r) => r == 'POST /v1/auth/refresh'), hasLength(1));
      final saved = store.credentials as ParentCredentials;
      expect((saved.accessToken, saved.refreshToken), ('new', 'r2'));
      expect(container.read(sessionProvider).value, isA<ParentCredentials>());
    });

    test('parent : renouvellement refusé → retour au premier lancement', () async {
      final store = MemoryCredentialStore(parent);
      server
        ..on('GET /v1/children', (_) => FakeServer.error(401, 'unauthorized', 'Session expirée.'))
        ..on(
          'POST /v1/auth/refresh',
          (_) => FakeServer.error(401, 'invalid_refresh_token', 'Reconnectez-vous.'),
        );
      final container = await start(server, store);
      await expectLater(container.read(apiProvider).children(), throwsA(isA<ApiException>()));
      expect(store.credentials, isA<NoCredentials>());
      expect(container.read(sessionProvider).value, isA<NoCredentials>());
    });

    test('parent : hors ligne pendant le renouvellement → la session est gardée', () async {
      final store = MemoryCredentialStore(parent);
      server
        ..on('GET /v1/children', (_) => FakeServer.error(401, 'unauthorized', 'Session expirée.'))
        ..on('POST /v1/auth/refresh', (_) => throw const SocketLikeException());
      final container = await start(server, store);
      await expectLater(container.read(apiProvider).children(), throwsA(isA<ApiException>()));
      expect(store.credentials, same(parent));
    });

    test('enfant : appareil délié par le parent → identifiants oubliés', () async {
      final store = MemoryCredentialStore(child);
      server.on('GET /v1/me', (_) => FakeServer.error(401, 'unauthorized', 'Appareil délié.'));
      final container = await start(server, store);
      await expectLater(container.read(apiProvider).me(), throwsA(isA<ApiException>()));
      expect(store.credentials, isA<NoCredentials>());
      expect(server.routes, isNot(contains('POST /v1/auth/refresh')));
    });

    test('déconnexion du parent : jeton de renouvellement révoqué côté serveur', () async {
      final store = MemoryCredentialStore(parent);
      server.on('POST /v1/auth/logout', (r) {
        expect(r.data, {'refresh_token': 'r1'});
        return (204, null);
      });
      final container = await start(server, store);
      await container.read(sessionProvider.notifier).signOut();
      expect(server.routes, ['POST /v1/auth/logout']);
      expect(store.credentials, isA<NoCredentials>());
    });
  });
}

/// Erreur levée par l'adaptateur : dio la présente comme une panne réseau.
class SocketLikeException implements Exception {
  const SocketLikeException();
}
