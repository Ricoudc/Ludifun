import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:webview_flutter/webview_flutter.dart';

import '../../core/api/api_exception.dart';
import '../../core/session.dart';
import '../../models/resource.dart';

/// Affiche la page d'une ressource ; `onScore` reçoit le score d'un exercice noté, `onBlocked`
/// une adresse hors du site, qui n'est pas ouverte.
abstract interface class ResourcePageBuilder {
  Widget build(
    LessonResource resource, {
    required ValueChanged<ResourceScore> onScore,
    required ValueChanged<Uri> onBlocked,
  });
}

/// La vraie page, dans une vue web de l'application (remplacée dans les tests).
class WebResourcePageBuilder implements ResourcePageBuilder {
  const WebResourcePageBuilder();

  @override
  Widget build(
    LessonResource resource, {
    required ValueChanged<ResourceScore> onScore,
    required ValueChanged<Uri> onBlocked,
  }) => _WebResourcePage(resource, onScore: onScore, onBlocked: onBlocked);
}

final resourcePageProvider = Provider<ResourcePageBuilder>((ref) => const WebResourcePageBuilder());

/// Les messages de la page (`postMessage`) sont transmis à l'application : MathALÉA y envoie le
/// score à la fin de l'exercice.
const _listenToScores = '''
(function () {
  if (window.__ludifun) return;
  window.__ludifun = true;
  window.addEventListener('message', function (event) {
    try {
      Ludifun.postMessage(typeof event.data === 'string' ? event.data : JSON.stringify(event.data));
    } catch (_) {}
  });
})();
''';

class _WebResourcePage extends StatefulWidget {
  const _WebResourcePage(this.resource, {required this.onScore, required this.onBlocked});

  final LessonResource resource;
  final ValueChanged<ResourceScore> onScore;
  final ValueChanged<Uri> onBlocked;

  @override
  State<_WebResourcePage> createState() => _WebResourcePageState();
}

class _WebResourcePageState extends State<_WebResourcePage> {
  late final WebViewController _controller;
  int _progress = 0;

  @override
  void initState() {
    super.initState();
    final provider = widget.resource.provider;
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..addJavaScriptChannel(
        'Ludifun',
        onMessageReceived: (message) {
          if (scoreFromMessage(message.message) case final score?) widget.onScore(score);
        },
      )
      ..setNavigationDelegate(
        NavigationDelegate(
          // La visionneuse reste sur le site : un lien vers un autre site n'est pas ouvert.
          onNavigationRequest: (request) {
            final uri = Uri.tryParse(request.url);
            if (!request.isMainFrame || (uri != null && provider.allows(uri))) {
              return NavigationDecision.navigate;
            }
            if (uri != null && uri.scheme != 'about') widget.onBlocked(uri);
            return NavigationDecision.prevent;
          },
          onProgress: (progress) {
            if (mounted) setState(() => _progress = progress);
          },
          onPageFinished: (_) => _controller.runJavaScript(_listenToScores),
        ),
      )
      ..loadRequest(widget.resource.url);
  }

  @override
  Widget build(BuildContext context) => Stack(
    children: [
      WebViewWidget(controller: _controller),
      if (_progress < 100) LinearProgressIndicator(value: _progress / 100),
    ],
  );
}

/// Une ressource ouverte dans l'application : l'enfant ne quitte pas Ludifun. Pour l'enfant, le
/// score d'un exercice noté est envoyé au serveur (le meilleur est montré au parent) ; il ne
/// change pas la maîtrise des notions, l'exercice n'étant pas corrigé par Ludifun.
class ResourceScreen extends ConsumerStatefulWidget {
  const ResourceScreen({required this.resource, this.lessonId, super.key});

  final LessonResource resource;

  /// `null` pour le parent qui regarde la ressource : aucun score n'est envoyé.
  final String? lessonId;

  @override
  ConsumerState<ResourceScreen> createState() => _ResourceScreenState();
}

class _ResourceScreenState extends ConsumerState<ResourceScreen> {
  ResourceScore? _sent;

  /// La page peut renvoyer le même score plusieurs fois : il n'est envoyé qu'une fois.
  Future<void> _score(ResourceScore score) async {
    final lessonId = widget.lessonId;
    if (lessonId == null || (_sent?.correct == score.correct && _sent?.total == score.total)) {
      return;
    }
    _sent = score;
    String message;
    try {
      await ref.read(apiProvider).postResourceResult(lessonId, widget.resource.id, score);
      message = score.correct == score.total
          ? '🎉 Bravo, tout est juste ! Score gardé : $score'
          : '👍 Score gardé : $score';
    } on ApiException catch (error) {
      message = error.message;
    }
    if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  void _blocked(Uri uri) => ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(content: Text('Ce lien mène à un autre site (${uri.host}) : il n\'est pas ouvert.')),
  );

  @override
  Widget build(BuildContext context) {
    final resource = widget.resource;
    return Scaffold(
      appBar: AppBar(
        title: Text(
          '${resource.provider.emoji} ${resource.title}',
          overflow: TextOverflow.ellipsis,
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: ref
                  .watch(resourcePageProvider)
                  .build(resource, onScore: _score, onBlocked: _blocked),
            ),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              child: Text(
                'Source : ${resource.licence}',
                style: const TextStyle(fontSize: 12, color: Colors.black54),
                textAlign: TextAlign.center,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
