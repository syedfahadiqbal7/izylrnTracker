import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/i18n.dart';
import '../../core/language_button.dart';
import '../../core/theme.dart';
import 'models.dart';
import 'providers.dart';

/// Parent ↔ watch chat (F23). Message thread + composer. Sending is Basic+; an offline
/// watch doesn't fail the send — the message is stored and shows as "queued".
class ChatScreen extends ConsumerStatefulWidget {
  final String childId;
  final String? childName;
  const ChatScreen({super.key, required this.childId, this.childName});

  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();
  bool _sending = false;
  int _lastCount = 0;

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _scrollToBottom({bool animate = true}) {
    // Defer to after the frame so the new content is laid out.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scroll.hasClients) return;
      final target = _scroll.position.maxScrollExtent;
      if (animate) {
        _scroll.animateTo(target,
            duration: const Duration(milliseconds: 250), curve: Curves.easeOut);
      } else {
        _scroll.jumpTo(target);
      }
    });
  }

  Future<void> _send() async {
    final text = _input.text.trim();
    if (text.isEmpty || _sending) return;
    setState(() => _sending = true);
    final t = ref.read(translatorProvider);
    try {
      await ref.read(chatActionsProvider).send(widget.childId, text);
      _input.clear();
      _scrollToBottom();
    } on ApiException catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
            content: Text(e.code == 'CHAT_REQUIRES_BASIC'
                ? t.t('chat.requires_basic', 'Upgrade to Basic plan to use chat.')
                : e.message)));
      }
    } finally {
      if (mounted) setState(() => _sending = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = ref.watch(translatorProvider);
    final messages = ref.watch(chatMessagesProvider(widget.childId));

    // Auto-scroll when new messages arrive.
    messages.whenData((list) {
      if (list.length != _lastCount) {
        _lastCount = list.length;
        _scrollToBottom(animate: _scroll.hasClients);
      }
    });

    return Scaffold(
      appBar: AppBar(
        titleSpacing: 20,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(t.t('chat.title', 'Chat'),
                style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 18)),
            Text(widget.childName ?? t.t('chat.subtitle', 'Message the watch'),
                style: TextStyle(
                    fontWeight: FontWeight.w500,
                    fontSize: 12.5,
                    color: Colors.grey.shade600)),
          ],
        ),
        actions: const [LanguageButton(), SizedBox(width: 4)],
      ),
      body: Column(
        children: [
          Expanded(
            child: messages.when(
              loading: () =>
                  const Center(child: CircularProgressIndicator(strokeWidth: 2.6)),
              error: (e, _) => _Error(
                message: e is ApiException
                    ? e.message
                    : t.t('chat.load_error', 'Could not load messages.'),
                retry: t.t('common.retry', 'Retry'),
                onRetry: () => ref.invalidate(chatMessagesProvider(widget.childId)),
              ),
              data: (list) => list.isEmpty
                  ? _Empty(
                      title: t.t('chat.empty', 'No messages yet'),
                      hint: t.t('chat.empty_hint',
                          'Send a short message to your child\'s watch.'),
                    )
                  : ListView.builder(
                      controller: _scroll,
                      padding: const EdgeInsets.fromLTRB(14, 14, 14, 8),
                      itemCount: list.length,
                      itemBuilder: (_, i) => _Bubble(message: list[i]),
                    ),
            ),
          ),
          _Composer(
            controller: _input,
            sending: _sending,
            onSend: _send,
            hint: t.t('chat.hint', 'Type a message…'),
          ),
        ],
      ),
    );
  }
}

class _Bubble extends ConsumerWidget {
  final ChatMessage message;
  const _Bubble({required this.message});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final t = ref.watch(translatorProvider);
    final mine = message.isMine;
    final bg = mine ? Brand.indigo : const Color(0xFFEFF2FB);
    final fg = mine ? Colors.white : Brand.ink;

    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
            maxWidth: MediaQuery.of(context).size.width * 0.78),
        margin: const EdgeInsets.only(bottom: 8),
        padding: const EdgeInsets.symmetric(horizontal: 13, vertical: 9),
        decoration: BoxDecoration(
          color: bg,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(16),
            topRight: const Radius.circular(16),
            bottomLeft: Radius.circular(mine ? 16 : 4),
            bottomRight: Radius.circular(mine ? 4 : 16),
          ),
        ),
        child: Column(
          crossAxisAlignment:
              mine ? CrossAxisAlignment.end : CrossAxisAlignment.start,
          children: [
            if (!mine)
              Padding(
                padding: const EdgeInsets.only(bottom: 2),
                child: Text(t.t('chat.watch', 'Watch'),
                    style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w700,
                        color: Brand.violet)),
              ),
            Text(message.content, style: TextStyle(color: fg, fontSize: 14.5)),
            const SizedBox(height: 3),
            Row(mainAxisSize: MainAxisSize.min, children: [
              Text(_time(message.createdAt),
                  style: TextStyle(
                      fontSize: 10.5,
                      color: mine ? Colors.white70 : Colors.grey.shade600)),
              if (mine) ...[
                const SizedBox(width: 4),
                _statusIcon(t),
              ],
            ]),
          ],
        ),
      ),
    );
  }

  Widget _statusIcon(Translator t) {
    switch (message.status) {
      case 'sent':
      case 'delivered':
        return const Icon(Icons.done_rounded, size: 13, color: Colors.white70);
      case 'failed':
        return const Icon(Icons.error_outline_rounded,
            size: 13, color: Color(0xFFFFD1D1));
      default: // queued
        return const Icon(Icons.schedule_rounded, size: 12, color: Colors.white70);
    }
  }

  String _time(DateTime dt) {
    final h = dt.hour.toString().padLeft(2, '0');
    final m = dt.minute.toString().padLeft(2, '0');
    return '$h:$m';
  }
}

class _Composer extends StatelessWidget {
  final TextEditingController controller;
  final bool sending;
  final VoidCallback onSend;
  final String hint;
  const _Composer({
    required this.controller,
    required this.sending,
    required this.onSend,
    required this.hint,
  });

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Container(
        padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
        decoration: BoxDecoration(
          color: Theme.of(context).scaffoldBackgroundColor,
          border: Border(top: BorderSide(color: Colors.grey.shade200)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: TextField(
                controller: controller,
                minLines: 1,
                maxLines: 4,
                maxLength: chatMaxChars,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => onSend(),
                decoration: InputDecoration(
                  hintText: hint,
                  isDense: true,
                  counterText: '', // custom counter below via buildCounter off
                  filled: true,
                  fillColor: const Color(0xFFF3F5FA),
                  contentPadding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(22),
                    borderSide: BorderSide.none,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 8),
            _SendButton(sending: sending, onSend: onSend),
          ],
        ),
      ),
    );
  }
}

class _SendButton extends StatelessWidget {
  final bool sending;
  final VoidCallback onSend;
  const _SendButton({required this.sending, required this.onSend});
  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 46,
      width: 46,
      child: Material(
        color: Brand.indigo,
        shape: const CircleBorder(),
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: sending ? null : onSend,
          child: sending
              ? const Padding(
                  padding: EdgeInsets.all(13),
                  child: CircularProgressIndicator(
                      strokeWidth: 2.2, color: Colors.white),
                )
              : const Icon(Icons.send_rounded, color: Colors.white, size: 20),
        ),
      ),
    );
  }
}

class _Empty extends StatelessWidget {
  final String title;
  final String hint;
  const _Empty({required this.title, required this.hint});
  @override
  Widget build(BuildContext context) => ListView(
        children: [
          const SizedBox(height: 100),
          Icon(Icons.chat_bubble_outline_rounded,
              size: 54, color: Colors.grey.shade400),
          const SizedBox(height: 14),
          Center(
              child: Text(title,
                  style: const TextStyle(
                      fontWeight: FontWeight.w700, fontSize: 16))),
          const SizedBox(height: 6),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 40),
            child: Text(hint,
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey.shade600)),
          ),
        ],
      );
}

class _Error extends StatelessWidget {
  final String message;
  final String retry;
  final VoidCallback onRetry;
  const _Error(
      {required this.message, required this.retry, required this.onRetry});
  @override
  Widget build(BuildContext context) => ListView(children: [
        const SizedBox(height: 120),
        Icon(Icons.cloud_off, size: 44, color: Colors.grey.shade400),
        const SizedBox(height: 12),
        Center(
            child: Text(message,
                style: const TextStyle(
                    color: Colors.red, fontWeight: FontWeight.w500))),
        const SizedBox(height: 12),
        Center(child: OutlinedButton(onPressed: onRetry, child: Text(retry))),
      ]);
}
