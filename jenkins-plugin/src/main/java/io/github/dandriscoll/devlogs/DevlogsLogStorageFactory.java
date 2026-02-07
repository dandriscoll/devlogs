package io.github.dandriscoll.devlogs;

import hudson.Extension;
import hudson.model.Job;
import hudson.model.Queue;
import hudson.model.Run;
import org.jenkinsci.plugins.workflow.flow.FlowExecutionOwner;
import org.jenkinsci.plugins.workflow.log.LogStorage;
import org.jenkinsci.plugins.workflow.log.LogStorageFactory;

import javax.annotation.Nonnull;
import java.io.IOException;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.logging.Level;
import java.util.logging.Logger;

/**
 * Factory that creates DevlogsLogStorage for pipeline builds that have
 * the devlogs option configured via DevlogsJobProperty.
 *
 * This captures ALL pipeline output including [Pipeline] annotations,
 * echo statements, stage messages, and command output.
 */
@Extension
public class DevlogsLogStorageFactory implements LogStorageFactory {
    private static final Logger LOGGER = Logger.getLogger(DevlogsLogStorageFactory.class.getName());

    // Cache of log storage instances by build ID
    private final Map<String, DevlogsLogStorage> storageCache = new ConcurrentHashMap<>();

    @Override
    public LogStorage forBuild(@Nonnull FlowExecutionOwner owner) {
        try {
            Queue.Executable executable = owner.getExecutable();
            if (!(executable instanceof Run)) {
                return null;
            }

            Run<?, ?> run = (Run<?, ?>) executable;
            Job<?, ?> job = run.getParent();

            // Check if devlogs is configured for this job
            DevlogsJobProperty property = job.getProperty(DevlogsJobProperty.class);
            if (property == null) {
                return null;
            }

            String buildId = run.getExternalizableId();

            String url = property.resolveUrl(run);
            if (url == null || url.trim().isEmpty()) {
                LOGGER.log(Level.WARNING, "Devlogs URL not configured for build " + buildId);
                return null;
            }

            return storageCache.computeIfAbsent(buildId, id ->
                new DevlogsLogStorage(
                    owner,
                    url,
                    property.getEffectiveApplication(run),
                    property.getComponent(),
                    property.getArea(),
                    property.getEnvironment(),
                    job.getFullName(),
                    run.getNumber(),
                    run.getUrl(),
                    buildId,
                    () -> storageCache.remove(id)
                )
            );

        } catch (IOException e) {
            LOGGER.log(Level.WARNING, "Error creating DevlogsLogStorage", e);
            return null;
        }
    }
}
