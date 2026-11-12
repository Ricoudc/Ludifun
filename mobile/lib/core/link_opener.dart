import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import 'session.dart';

/// Ouvre une page web dans le navigateur (politique de confidentialité…).
abstract interface class LinkOpener {
  Future<bool> open(Uri uri);
}

class BrowserLinkOpener implements LinkOpener {
  const BrowserLinkOpener();

  @override
  Future<bool> open(Uri uri) => launchUrl(uri, mode: LaunchMode.externalApplication);
}

final linkOpenerProvider = Provider<LinkOpener>((ref) => const BrowserLinkOpener());

/// Pages publiques servies par l'API : `/confidentialite`, `/suppression-compte`.
Future<bool> openPublicPage(WidgetRef ref, String path) => ref
    .read(linkOpenerProvider)
    .open(Uri.parse('${ref.read(bareDioProvider).options.baseUrl}$path'));
