turn内component_timeline 内容太冗长了, 只要关键的节点:
assistant-runtime: 
    - 发送请求(grpc)
    - 第一次接收到回复/收到回复结束
    - 发起打断
    - tool call start/end
    - error
nca:
   - tool call start/end
   - llm request start/end
   - 生成回复(start/end)
   - error
aig:
   - tool call start/end
   - 调用agent-service start/end
   - error
gmg:
   - llm request start/end
   - 生成回复(start/end)
   - error
agent-service:
   - tool call start/end
   - error

duration

greeting:

ar(assistant-runtime): [state: greeting] Generating greeting -> ar: Received GenerateEvent
 
-> nca: Sending greeting message 
普通聊天
assistant-runtime: 