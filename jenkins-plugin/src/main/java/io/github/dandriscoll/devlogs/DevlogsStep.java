package io.github.dandriscoll.devlogs;

import com.google.gson.Gson;
import com.google.gson.JsonObject;
import hudson.Extension;
import hudson.console.ConsoleLogFilter;
import hudson.model.Run;
import okhttp3.*;
import org.jenkinsci.plugins.workflow.steps.*;
import org.kohsuke.stapler.DataBoundConstructor;
import org.kohsuke.stapler.DataBoundSetter;

import javax.annotation.Nonnull;
import java.io.IOException;
import java.io.OutputStream;
import java.io.Serializable;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Set;
import java.util.concurrent.atomic.AtomicInteger;

/**
 * Pipeline step that wraps build execution and streams logs to a devlogs instance.
 * 
 * Example usage in Jenkinsfile:
 * <pre>
 * devlogs(url: 'https://admin:password@opensearch.example.com:9200/devlogs-myproject') {
 *     // Your build steps here
 *     sh 'make build'
 * }
 * </pre>
 */
public class DevlogsStep extends Step implements Serializable {
    private static final long serialVersionUID = 1L;

    private final String url;
    private String index;
    
    @DataBoundConstructor
    public DevlogsStep(String url) {
        this.url = url;
    }
    
    public String getUrl() {
        return url;
    }
    
    public String getIndex() {
        return index;
    }
    
    @DataBoundSetter
    public void setIndex(String index) {
        this.index = index;
    }
    
    @Override
    public StepExecution start(StepContext context) throws Exception {
        return new DevlogsStepExecution(context, url, index);
    }
    
    @Extension
    public static class DescriptorImpl extends StepDescriptor {
        
        @Override
        public String getFunctionName() {
            return "devlogs";
        }
        
        @Nonnull
        @Override
        public String getDisplayName() {
            return "Stream logs to Devlogs";
        }
        
        @Override
        public boolean takesImplicitBlockArgument() {
            return true;
        }
        
        @Override
        public Set<? extends Class<?>> getRequiredContext() {
            return Set.of(Run.class);
        }
    }
    
    /**
     * Execution for the devlogs step.
     */
    public static class DevlogsStepExecution extends AbstractStepExecutionImpl {
        private static final long serialVersionUID = 1L;
        
        private final String url;
        private final String index;
        private transient DevlogsConsoleLogFilter filter;
        
        public DevlogsStepExecution(StepContext context, String url, String index) {
            super(context);
            this.url = url;
            this.index = index;
        }
        
        @Override
        public boolean start() throws Exception {
            if (url == null || url.trim().isEmpty()) {
                // No URL provided, just pass through
                getContext().newBodyInvoker().withCallback(BodyExecutionCallback.wrap(getContext())).start();
                return false;
            }
            
            Run<?, ?> run = getContext().get(Run.class);
            if (run == null) {
                throw new IllegalStateException("Run context is not available");
            }
            
            // Create and register the log filter
            filter = new DevlogsConsoleLogFilter(url, index, run);
            
            getContext().newBodyInvoker()
                .withContext(BodyInvoker.mergeConsoleLogFilters(getContext().get(ConsoleLogFilter.class), filter))
                .withCallback(BodyExecutionCallback.wrap(getContext()))
                .start();
            
            return false;
        }
        
        @Override
        public void stop(@Nonnull Throwable cause) throws Exception {
            if (filter != null) {
                filter.close();
            }
            getContext().onFailure(cause);
        }
    }
    
    /**
     * Console log filter that intercepts and streams logs to devlogs.
     */
    private static class DevlogsConsoleLogFilter extends ConsoleLogFilter implements Serializable {
        private static final long serialVersionUID = 1L;
        
        private final String url;
        private final String index;
        private final String runId;
        private final String jobName;
        private final int buildNumber;
        private final String buildUrl;
        private final AtomicInteger seq = new AtomicInteger(0);
        
        public DevlogsConsoleLogFilter(String url, String index, Run<?, ?> run) {
            this.url = url;
            
            // Extract index from URL if not provided separately
            if (index == null || index.trim().isEmpty()) {
                this.index = extractIndexFromUrl(url);
            } else {
                this.index = index;
            }
            
            this.runId = run.getExternalizableId();
            this.jobName = run.getParent().getFullName();
            this.buildNumber = run.getNumber();
            this.buildUrl = run.getUrl();
        }
        
        private String extractIndexFromUrl(String url) {
            // URL format: https://user:pass@host:port/index
            // or https://host:port/index
            try {
                int lastSlash = url.lastIndexOf('/');
                if (lastSlash > 0 && lastSlash < url.length() - 1) {
                    return url.substring(lastSlash + 1);
                }
            } catch (Exception e) {
                // Fall back to default
            }
            return "devlogs";
        }
        
        private String getBaseUrl() {
            // Remove index from URL to get base
            int lastSlash = url.lastIndexOf('/');
            if (lastSlash > 0) {
                return url.substring(0, lastSlash);
            }
            return url;
        }
        
        @Override
        public OutputStream decorateLogger(Run build, OutputStream logger) throws IOException, InterruptedException {
            return new DevlogsOutputStream(logger, url, index, runId, jobName, buildNumber, buildUrl, seq);
        }

        public void close() {
            // Cleanup if needed
        }
    }
    
    /**
     * OutputStream that captures log lines and sends them to devlogs.
     */
    private static class DevlogsOutputStream extends OutputStream implements Serializable {
        private static final long serialVersionUID = 1L;
        private static final int BUFFER_SIZE = 8192;
        private static final int BATCH_SIZE = 10;
        private static final long BATCH_TIMEOUT_MS = 10000; // 10 seconds
        
        private final OutputStream delegate;
        private final String baseUrl;
        private final String index;
        private final String runId;
        private final String jobName;
        private final int buildNumber;
        private final String buildUrl;
        private final AtomicInteger seq;
        
        private final byte[] buffer = new byte[BUFFER_SIZE];
        private int bufferPos = 0;
        private final StringBuilder lineBuffer = new StringBuilder();
        private final StringBuilder batchBuffer = new StringBuilder();
        private int batchCount = 0;
        private long lastBatchTime = System.currentTimeMillis();
        private String currentLineTimestamp = null;  // Timestamp for current line being built
        
        private transient OkHttpClient client;
        private transient Gson gson;
        
        public DevlogsOutputStream(OutputStream delegate, String url, String index, String runId, 
                                   String jobName, int buildNumber, String buildUrl, AtomicInteger seq) {
            this.delegate = delegate;
            this.index = index;
            this.runId = runId;
            this.jobName = jobName;
            this.buildNumber = buildNumber;
            this.buildUrl = buildUrl;
            this.seq = seq;
            
            // Extract base URL (without index)
            int lastSlash = url.lastIndexOf('/');
            if (lastSlash > 0) {
                this.baseUrl = url.substring(0, lastSlash);
            } else {
                this.baseUrl = url;
            }
            
            initTransients();
        }
        
        private void initTransients() {
            if (client == null) {
                client = new OkHttpClient.Builder()
                    .followRedirects(true)
                    .followSslRedirects(true)
                    .build();
            }
            if (gson == null) {
                gson = new Gson();
            }
        }
        
        @Override
        public void write(int b) throws IOException {
            // Write to delegate
            delegate.write(b);
            
            // Buffer for line processing
            buffer[bufferPos++] = (byte) b;
            
            if (b == '\n' || bufferPos >= BUFFER_SIZE) {
                processBuffer();
            }
        }
        
        @Override
        public void write(byte[] b, int off, int len) throws IOException {
            // Write to delegate
            delegate.write(b, off, len);
            
            // Process for devlogs
            for (int i = 0; i < len; i++) {
                buffer[bufferPos++] = b[off + i];
                
                if (b[off + i] == '\n' || bufferPos >= BUFFER_SIZE) {
                    processBuffer();
                }
            }
        }
        
        @Override
        public void flush() throws IOException {
            delegate.flush();
            if (bufferPos > 0) {
                processBuffer();
            }
            if (lineBuffer.length() > 0) {
                String timestamp = (currentLineTimestamp != null) ? currentLineTimestamp : Instant.now().toString();
                sendLine(lineBuffer.toString(), timestamp);
                lineBuffer.setLength(0);
                currentLineTimestamp = null;
            }
            flushBatch();
        }
        
        @Override
        public void close() throws IOException {
            flush();
            delegate.close();
        }
        
        private void processBuffer() {
            if (bufferPos == 0) return;
            
            String text = new String(buffer, 0, bufferPos, StandardCharsets.UTF_8);
            bufferPos = 0;
            
            for (char c : text.toCharArray()) {
                if (c == '\n') {
                    if (lineBuffer.length() > 0) {
                        // Use the timestamp captured when line started, or capture now if not set
                        String timestamp = (currentLineTimestamp != null) ? currentLineTimestamp : Instant.now().toString();
                        sendLine(lineBuffer.toString(), timestamp);
                        lineBuffer.setLength(0);
                        currentLineTimestamp = null;
                    }
                } else {
                    // Capture timestamp when line starts
                    if (lineBuffer.length() == 0 && currentLineTimestamp == null) {
                        currentLineTimestamp = Instant.now().toString();
                    }
                    lineBuffer.append(c);
                }
            }
        }
        
        private void sendLine(String line, String timestamp) {
            if (line.trim().isEmpty()) return;
            
            try {
                initTransients();
                
                // Check if batch timeout has elapsed
                long currentTime = System.currentTimeMillis();
                if (batchCount > 0 && (currentTime - lastBatchTime) >= BATCH_TIMEOUT_MS) {
                    flushBatch();
                }
                
                JsonObject doc = new JsonObject();
                doc.addProperty("doc_type", "log_entry");
                doc.addProperty("timestamp", timestamp);  // Use the timestamp from when line was written
                doc.addProperty("run_id", runId);
                doc.addProperty("job", jobName);
                doc.addProperty("build_number", buildNumber);
                doc.addProperty("build_url", buildUrl);
                doc.addProperty("seq", seq.incrementAndGet());
                doc.addProperty("message", line);
                doc.addProperty("source", "jenkins");
                doc.addProperty("level", "info");
                
                // Add to batch
                batchBuffer.append("{\"index\":{\"_index\":\"").append(index).append("\"}}\n");
                batchBuffer.append(gson.toJson(doc)).append("\n");
                batchCount++;
                
                // Update last batch time on first entry
                if (batchCount == 1) {
                    lastBatchTime = currentTime;
                }
                
                // Flush if batch is full
                if (batchCount >= BATCH_SIZE) {
                    flushBatch();
                }
            } catch (Exception e) {
                // Don't fail the build if logging fails
                System.err.println("Warning: Failed to send log to devlogs: " + e.getMessage());
            }
        }
        
        private void flushBatch() {
            if (batchCount == 0) return;
            
            try {
                initTransients();
                
                String bulkUrl = baseUrl + "/_bulk";
                RequestBody body = RequestBody.create(
                    batchBuffer.toString(),
                    MediaType.parse("application/x-ndjson")
                );
                
                Request request = new Request.Builder()
                    .url(bulkUrl)
                    .post(body)
                    .build();
                
                try (Response response = client.newCall(request).execute()) {
                    if (!response.isSuccessful()) {
                        System.err.println("Warning: Devlogs bulk request failed: " + response.code());
                    }
                }
                
                batchBuffer.setLength(0);
                batchCount = 0;
                lastBatchTime = System.currentTimeMillis();
            } catch (Exception e) {
                System.err.println("Warning: Failed to flush logs to devlogs: " + e.getMessage());
                batchBuffer.setLength(0);
                batchCount = 0;
                lastBatchTime = System.currentTimeMillis();
            }
        }
    }
}
