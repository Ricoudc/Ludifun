import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:ludifun/core/storage/credentials.dart';

void main() {
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));

  test('les identifiants des deux espaces survivent à un redémarrage', () async {
    final store = SecureCredentialStore();
    expect(await store.read(), isA<NoCredentials>());

    await store.write(
      const ParentCredentials(accessToken: 'a', refreshToken: 'r', email: 'p@example.fr'),
    );
    final parent = await SecureCredentialStore().read() as ParentCredentials;
    expect((parent.accessToken, parent.refreshToken, parent.email), ('a', 'r', 'p@example.fr'));

    await store.write(
      const ChildCredentials(deviceToken: 'ldf_d_x', childId: 'c1', displayName: 'Emma'),
    );
    final child = await SecureCredentialStore().read() as ChildCredentials;
    expect((child.deviceToken, child.childId, child.displayName), ('ldf_d_x', 'c1', 'Emma'));

    await store.write(const NoCredentials());
    expect(await const FlutterSecureStorage().read(key: SecureCredentialStore.key), isNull);
  });

  test('un contenu illisible vaut « aucun identifiant »', () async {
    for (final raw in ['pas du json', '[1, 2]', '{"space": "parent"}', '{"space": 3}']) {
      FlutterSecureStorage.setMockInitialValues({SecureCredentialStore.key: raw});
      expect(await SecureCredentialStore().read(), isA<NoCredentials>(), reason: raw);
    }
  });
}
