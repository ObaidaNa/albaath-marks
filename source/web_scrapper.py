import asyncio
from dataclasses import dataclass
from typing import List

import aiohttp

UNIVERSITY_URL = "https://exam.albaath-univ.edu.sy/exam-it/re.php"


@dataclass
class WebStudentResponse:
    student_number: int
    html_page: bytes


async def multi_async_request(
    numbers: List[int], recurse_limit: int = 2
) -> List[WebStudentResponse]:
    async with aiohttp.ClientSession() as session:
        tasks = [
            asyncio.create_task(one_req(int(number), session, recurse_limit))
            for number in numbers
        ]
        gathered = await asyncio.gather(*tasks)
    return gathered


async def one_req(
    number, session: aiohttp.ClientSession, recurse_limit: int
) -> WebStudentResponse:
    if recurse_limit <= 0:
        raise Exception("uncompleted request, try again later")

    try:
        async with session.post(UNIVERSITY_URL, data={"number1": number}) as req:
            res_data = await req.read()
        if req.status != 200:
            await asyncio.sleep(0.5)
            return await one_req(number, session, recurse_limit - 1)
        return WebStudentResponse(number, res_data)
    except Exception:
        await asyncio.sleep(0.5)
        return await one_req(number, session, recurse_limit - 1)
