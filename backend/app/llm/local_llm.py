import asyncio
from collections.abc import (
    Awaitable,
    Callable,
)

from transformers import (
    AsyncTextIteratorStreamer,
    pipeline,
)


StreamCallback = Callable[
    [str],
    Awaitable[None],
]


class LocalLLM:

    def __init__(self):

        self.model_name = (
            "Qwen/Qwen2.5-0.5B-Instruct"
        )

        print(
            "LOADING LOCAL MODEL:",
            self.model_name,
        )

        self.generator = pipeline(
            task="text-generation",
            model=self.model_name,
            device_map="auto",
        )

        print(
            "LOCAL MODEL READY:",
            self.model_name,
        )

    # ==================================================
    # Normal generation
    # ==================================================

    def _generate_sync(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 256,
    ) -> str:

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ]

        result = self.generator(
            messages,
            max_new_tokens=max_new_tokens,
            do_sample=False,
        )

        generated = result[0][
            "generated_text"
        ]

        if isinstance(
            generated,
            list,
        ):

            for message in reversed(
                generated
            ):

                if (
                    message.get("role")
                    == "assistant"
                ):

                    return message[
                        "content"
                    ].strip()

        return str(
            generated
        ).strip()

    async def generate(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        max_new_tokens: int = 256,
    ) -> str:

        return await asyncio.to_thread(
            self._generate_sync,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_new_tokens=max_new_tokens,
        )

    # ==================================================
    # Streaming generation
    # ==================================================

    async def generate_stream(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        on_chunk: StreamCallback,
        max_new_tokens: int = 256,
    ) -> str:
        """
        真正流式生成。

        行为：

        model.generate()
            ↓
        AsyncTextIteratorStreamer
            ↓
        on_chunk(text)
            ↓
        同时累积完整 answer
            ↓
        return full_answer
        """

        tokenizer = (
            self.generator.tokenizer
        )

        model = (
            self.generator.model
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ]

        # ------------------------------------------
        # 1. 构造 Qwen chat prompt
        # ------------------------------------------

        prompt = (
            tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        )

        # ------------------------------------------
        # 2. tokenize
        # ------------------------------------------

        inputs = tokenizer(
            prompt,
            return_tensors="pt",
        )

        # pipeline(device_map="auto")
        # 当前 Qwen 0.5B 通常在单一设备。
        device = model.device

        inputs = {
            key: value.to(device)
            for key, value
            in inputs.items()
        }

        # ------------------------------------------
        # 3. Streamer
        # ------------------------------------------

        streamer = (
            AsyncTextIteratorStreamer(
                tokenizer,
                skip_prompt=True,
                skip_special_tokens=True,

                # generation thread 出现问题时，
                # 不允许这里永久等待。
                timeout=60.0,
            )
        )

        generation_kwargs = {
            **inputs,

            "streamer": streamer,

            "max_new_tokens":
                max_new_tokens,

            "do_sample":
                False,

            "pad_token_id":
                tokenizer.eos_token_id,
        }

        # ------------------------------------------
        # 4. model.generate 是阻塞操作
        #
        # 放到独立 thread，
        # asyncio event loop 继续消费 streamer。
        # ------------------------------------------

        generation_task = (
            asyncio.create_task(
                asyncio.to_thread(
                    model.generate,
                    **generation_kwargs,
                )
            )
        )

        chunks: list[str] = []

        try:

            async for chunk in streamer:

                if not chunk:
                    continue

                chunks.append(
                    chunk
                )

                # 立刻向 LangGraph 上层报告
                await on_chunk(
                    chunk
                )

            # 这里非常重要：
            # streamer结束以后仍检查 model.generate
            # 本身有没有抛异常。
            await generation_task

        except asyncio.CancelledError:

            # Worker lease lost 时，
            # 上层会取消 ChatService。
            #
            # cancellation 必须继续传播。
            raise

        except TimeoutError:

            # 如果 generation thread 已经异常退出，
            # 优先把模型本身异常重新抛出来。
            if generation_task.done():
                await generation_task

            raise RuntimeError(
                "Local model streaming timed out"
            )

        # ------------------------------------------
        # 5. 返回完整答案
        # ------------------------------------------

        answer = "".join(
            chunks
        ).strip()

        return answer


local_llm = LocalLLM()