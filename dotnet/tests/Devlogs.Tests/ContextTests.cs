using Devlogs.Context;
using Xunit;

namespace Devlogs.Tests;

public class ContextTests
{
    [Fact]
    public void GetOperationId_WhenNotSet_ReturnsNull()
    {
        // Arrange
        var context = new DevlogsContext();

        // Act
        var operationId = context.GetOperationId();

        // Assert
        Assert.Null(operationId);
    }

    [Fact]
    public void GetArea_WhenNotSet_ReturnsNull()
    {
        // Arrange
        var context = new DevlogsContext();

        // Act
        var area = context.GetArea();

        // Assert
        Assert.Null(area);
    }

    [Fact]
    public void SetArea_SetsAreaValue()
    {
        // Arrange
        var context = new DevlogsContext();

        // Act
        context.SetArea("test-area");
        var area = context.GetArea();

        // Assert
        Assert.Equal("test-area", area);
    }

    [Fact]
    public void BeginOperation_WithOperationId_SetsOperationId()
    {
        // Arrange
        var context = new DevlogsContext();
        var expectedOperationId = "test-op-123";

        // Act
        using (context.BeginOperation(expectedOperationId))
        {
            var operationId = context.GetOperationId();

            // Assert
            Assert.Equal(expectedOperationId, operationId);
        }
    }

    [Fact]
    public void BeginOperation_WithoutOperationId_GeneratesGuid()
    {
        // Arrange
        var context = new DevlogsContext();

        // Act
        using (context.BeginOperation())
        {
            var operationId = context.GetOperationId();

            // Assert
            Assert.NotNull(operationId);
            Assert.True(Guid.TryParse(operationId, out _));
        }
    }

    [Fact]
    public void BeginOperation_WithArea_SetsArea()
    {
        // Arrange
        var context = new DevlogsContext();

        // Act
        using (context.BeginOperation(area: "test-area"))
        {
            var area = context.GetArea();

            // Assert
            Assert.Equal("test-area", area);
        }
    }

    [Fact]
    public void BeginOperation_RestoresContextOnDispose()
    {
        // Arrange
        var context = new DevlogsContext();
        var outerOperationId = "outer-op";
        var innerOperationId = "inner-op";

        // Act & Assert
        using (context.BeginOperation(outerOperationId, "outer-area"))
        {
            Assert.Equal(outerOperationId, context.GetOperationId());
            Assert.Equal("outer-area", context.GetArea());

            using (context.BeginOperation(innerOperationId, "inner-area"))
            {
                Assert.Equal(innerOperationId, context.GetOperationId());
                Assert.Equal("inner-area", context.GetArea());
            }

            // Inner scope disposed, should restore outer values
            Assert.Equal(outerOperationId, context.GetOperationId());
            Assert.Equal("outer-area", context.GetArea());
        }

        // Outer scope disposed, should restore null values
        Assert.Null(context.GetOperationId());
        Assert.Null(context.GetArea());
    }

    [Fact]
    public async Task BeginOperation_WorksAcrossAsyncBoundaries()
    {
        // Arrange
        var context = new DevlogsContext();
        var expectedOperationId = "async-op-123";

        // Act & Assert
        using (context.BeginOperation(expectedOperationId, "async-area"))
        {
            Assert.Equal(expectedOperationId, context.GetOperationId());

            await Task.Run(() =>
            {
                // Context should be preserved in async continuations
                Assert.Equal(expectedOperationId, context.GetOperationId());
                Assert.Equal("async-area", context.GetArea());
            });
        }
    }
}
