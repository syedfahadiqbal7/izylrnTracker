/// A chat message between a parent and the child's watch (mirrors backend
/// ChatMessageResponse, F23). `sender_type` is 'parent' (outgoing) or 'child' (inbound
/// from the watch). `status` is queued | sent | delivered | failed.
class ChatMessage {
  final String id;
  final String childId;
  final String senderType; // 'parent' | 'child'
  final String content;
  final String status; // queued | sent | delivered | failed
  final DateTime createdAt;

  const ChatMessage({
    required this.id,
    required this.childId,
    required this.senderType,
    required this.content,
    required this.status,
    required this.createdAt,
  });

  /// Sent by the parent (this side) → right-aligned bubble.
  bool get isMine => senderType == 'parent';

  factory ChatMessage.fromJson(Map<String, dynamic> j) => ChatMessage(
        id: j['id'] as String,
        childId: j['child_id'] as String,
        senderType: (j['sender_type'] ?? 'parent') as String,
        content: (j['content'] ?? '') as String,
        status: (j['status'] ?? 'queued') as String,
        createdAt: DateTime.parse(j['created_at'] as String).toLocal(),
      );
}

/// Matches the backend column cap (chat_messages.content) + ChatSendRequest.
const chatMaxChars = 120;
