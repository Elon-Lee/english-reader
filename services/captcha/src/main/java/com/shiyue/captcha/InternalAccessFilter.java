package com.shiyue.captcha;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

import javax.servlet.FilterChain;
import javax.servlet.ServletException;
import javax.servlet.ReadListener;
import javax.servlet.ServletInputStream;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletRequestWrapper;
import javax.servlet.http.HttpServletResponse;
import java.io.ByteArrayInputStream;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
class InternalAccessFilter extends OncePerRequestFilter {
    private final byte[] secret;

    InternalAccessFilter(@Value("${shiyue.captcha.secret:}") String secret) {
        if (secret.length() < 32) {
            throw new IllegalArgumentException("SHIYUE_CAPTCHA_SECRET must contain at least 32 characters");
        }
        this.secret = secret.getBytes(StandardCharsets.UTF_8);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        response.setHeader("Cache-Control", "no-store");
        String path = request.getServletPath();
        if (path.isEmpty()) path = request.getRequestURI();
        // Spring may normalize path parameters before routing. Protect every route
        // except the exact safe health endpoint, including alternate path spellings.
        if (!path.equals("/health") || !request.getMethod().equals("GET")) {
            String supplied = request.getHeader("X-Captcha-Secret");
            if (supplied == null || !MessageDigest.isEqual(secret, supplied.getBytes(StandardCharsets.UTF_8))) {
                response.setStatus(401);
                response.setContentType("application/json");
                response.getWriter().write("{\"code\":401,\"success\":false,\"msg\":\"Unauthorized\",\"data\":null}");
                return;
            }
        }
        if (request.getMethod().equals("POST")) {
            if (request.getContentLengthLong() > 65536) {
                tooLarge(response);
                return;
            }
            byte[] body = request.getInputStream().readNBytes(65537);
            if (body.length > 65536) {
                tooLarge(response);
                return;
            }
            request = new BufferedRequest(request, body);
        }
        chain.doFilter(request, response);
    }

    private void tooLarge(HttpServletResponse response) throws IOException {
        response.setStatus(413);
        response.setContentType("application/json");
        response.getWriter().write("{\"code\":413,\"success\":false,\"msg\":\"Request too large\",\"data\":null}");
    }

    private static class BufferedRequest extends HttpServletRequestWrapper {
        private final byte[] body;

        BufferedRequest(HttpServletRequest request, byte[] body) {
            super(request);
            this.body = body;
        }

        @Override
        public ServletInputStream getInputStream() {
            ByteArrayInputStream input = new ByteArrayInputStream(body);
            return new ServletInputStream() {
                public int read() { return input.read(); }
                public boolean isFinished() { return input.available() == 0; }
                public boolean isReady() { return true; }
                public void setReadListener(ReadListener listener) { throw new UnsupportedOperationException(); }
            };
        }

        @Override
        public BufferedReader getReader() {
            return new BufferedReader(new InputStreamReader(getInputStream(), StandardCharsets.UTF_8));
        }
    }
}
