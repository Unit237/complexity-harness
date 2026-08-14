def route_request(request, retries):
    if request is None:
        return "missing"
    if request.cached and request.valid:
        return request.value
    for attempt in range(retries):
        try:
            if attempt > 1 or request.force:
                return request.send()
        except TimeoutError:
            if attempt + 1 == retries:
                raise
    return None
